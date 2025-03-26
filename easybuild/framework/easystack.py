# Copyright 2020-2025 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Support for easybuild-ing from multiple easyconfigs based on
information obtained from provided file (easystack) with build specifications.

Authors:

* Denis Kristak (Inuits)
* Pavel Grochal (Inuits)
* Kenneth Hoste (HPC-UGent)
* Caspar van Leeuwen (SURF)
"""
import contextlib
import pprint

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file
from easybuild.tools.utilities import only_if_module_is_available

with contextlib.suppress(ImportError):
    import yaml

EASYSTACK_DOC_URL = 'https://docs.easybuild.io/en/latest/Easystack-files.html'

EASYSTACK_EC_KEY = 'easyconfigs'
EASYSTACK_EB_VER_KEY = 'easybuild_version'

_log = fancylogger.getLogger('easystack', fname=False)


def check_value(value, context):
    """
    Check whether specified value obtained from a YAML file in specified context represents is valid.
    The value must be a string (not a float or an int).
    """
    if not isinstance(value, str):
        error_msg = '\n'.join([
            "Value %(value)s (of type %(type)s) obtained for %(context)s is not valid!",
            "Make sure to wrap the value in single quotes (like '%(value)s') to avoid that it is interpreted "
            "by the YAML parser as a non-string value.",
        ])
        format_info = {
            'context': context,
            'type': type(value),
            'value': value,
        }
        raise EasyBuildError(error_msg % format_info)


class EasyStack:
    """
    Contains list of easyconfigs and their options
    Provides utility methods to parse easystacks
    """

    def __init__(self, easystack_path):
        """Convert given easystack file into an EasyStack"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.easyconfigs = []
        self.easybuild_version = None

        self.parse(easystack_path)

    def __str__(self):
        """Pretty printing of an EasyStack instance"""
        return pprint.pformat(self.ec_opt_tuples)

    @property
    def ec_opt_tuples(self):
        """
        List of easyconfigs with their specific options and general build options
        """

        return self.easyconfigs

    @only_if_module_is_available('yaml', pkgname='PyYAML')
    def parse(self, easystack_path):
        """
        Parse YAML file and assigns obtained values to SW config instances as well as general config instance
        """
        yaml_txt = read_file(easystack_path)

        try:
            easystack = yaml.safe_load(yaml_txt)
        except (yaml.YAMLError, yaml.scanner.ScannerError) as err:
            raise EasyBuildError(f"Failed to parse easystack '{easystack_path}': {err}") from err

        # parse list of easyconfigs
        if EASYSTACK_EC_KEY not in easystack:
            raise EasyBuildError(f"Top-level key '{EASYSTACK_EC_KEY}' missing in easystack file: {easystack_path}")

        easystack_easyconfigs = easystack[EASYSTACK_EC_KEY]

        if not isinstance(easystack_easyconfigs, list):
            ec_data_type = type(easystack_easyconfigs)
            msg = '\n'.join([
                f"Key '{EASYSTACK_EC_KEY}' in easystack '{easystack_path}' should be a list, found {ec_data_type}",
                f"Make sure you use '-' to create list items under '{EASYSTACK_EC_KEY}', for example:",
                f"    '{EASYSTACK_EC_KEY}':",
                "        - example-1.0.eb",
                "        - example-2.0.eb:",
                "            options:"
                "              ...",
            ])
            raise EasyBuildError(msg)

        self.easyconfigs = [self.parse_easyconfig_spec(ec_spec) for ec_spec in easystack_easyconfigs]

        # parse other options in easystack
        self.easybuild_version = easystack.get(EASYSTACK_EB_VER_KEY, None)

        easyconfigs_log_print = '\n'.join([ec[0] for ec in self.easyconfigs])
        self.log.debug(f"Parsed easystack:\n{easyconfigs_log_print}")

        return True

    @staticmethod
    def parse_easyconfig_spec(ec_spec):
        """
        Parse easyconfig specification in easystack file
        """

        ec_filename = None
        if isinstance(ec_spec, str):
            ec_filename = ec_spec
            ec_opts = {}
        elif isinstance(ec_spec, dict):
            # only one easyconfig per spec allowed
            if len(ec_spec) > 1:
                raise EasyBuildError(
                    "EasyConfig definition in EasyStack can only provide one file name, "
                    f"found {len(ec_spec)}: {', '.join(ec_spec.keys())}. "
                    f"See {EASYSTACK_DOC_URL} for documentation."
                )
            ec_filename = next(iter(ec_spec))
            ec_opts = ec_spec[ec_filename] or {}

        # build options cannot be a dict
        # TODO: make smarter and check actual vailidity of options passed before going into build
        if any([isinstance(ec_opts[opt], dict) for opt in ec_opts]):
            raise EasyBuildError(
                f"Found one or more invalid options for easyconfig '{ec_filename}' in EasyStack. "
                "Options cannot be a dictionary."
            )

        if not ec_filename.endswith('.eb'):
            ec_filename += '.eb'

        return (ec_filename, ec_opts)

class EasyStackParser:
    """DEPRECATED: Parser for easystack files (in YAML syntax)."""

    def __init__(self):
        """DEPRECATED: parser class for easystacks"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

    @staticmethod
    def parse(filepath):
        """
        DEPRECATED: Parses YAML file and assigns obtained values to SW config
        instances as well as general config instance
        """
        _log.deprecated(
            "EasyStackParse.parse() is deprecated, use EasyStack.parse() instead",
            '6.0',
        )
        return EasyStack(filepath)

    @staticmethod
    def parse_by_easyconfigs(filepath, easyconfigs, easybuild_version=None, robot=False):
        """
        DEPRECATED: Parse easystack file with 'easyconfigs' as top-level key.
        """
        _log.deprecated(
            "EasyStackParse.parse_by_easyconfig() is deprecated, use EasyStack.parse_easyconfig_spec() instead",
            '6.0',
        )
        return EasyStack(filepath)

@only_if_module_is_available('yaml', pkgname='PyYAML')
def parse_easystack(filepath):
    """DEPRECATED: Parses through easystack file, returns what EC are to be installed together with their options."""
    _log.deprecated(
        "parse_easystack() is deprecated, use EasyStack.parse() instead",
        '6.0',
    )
    return EasyStack(filepath)
