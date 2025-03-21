# #
# Copyright 2015-2025 Ghent University
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
# #

"""
Support for checking types of easyconfig parameter values.

Authors:

* Caroline De Brouwer (Ghent University)
* Kenneth Hoste (Ghent University)
"""

from easybuild.base import fancylogger
from easybuild.framework.easyconfig.format.format import DEPENDENCY_PARAMETERS
from easybuild.framework.easyconfig.format.format import SANITY_CHECK_PATHS_DIRS, SANITY_CHECK_PATHS_FILES
from easybuild.tools.build_log import EasyBuildError

_log = fancylogger.getLogger('easyconfig.types', fname=False)


def as_hashable(dict_value):
    """Helper function, convert dict value to hashable equivalent via tuples."""
    res = []
    for key, val in sorted(dict_value.items()):
        if isinstance(val, list):
            val = tuple(val)
        elif isinstance(val, dict):
            val = as_hashable(val)
        res.append((key, val))
    return tuple(res)


def check_element_types(elems, allowed_types):
    """
    Check whether types of elements of specified (iterable) value are as expected.

    :param elems: iterable value (list or dict) of elements
    :param allowed_types: allowed types per element; either a simple list, or a dict of allowed_types by element name
    """
    # combine elements with their list of allowed types
    elems_and_allowed_types = None
    if isinstance(elems, (list, tuple)):
        if isinstance(allowed_types, (list, tuple)):
            elems_and_allowed_types = [(elem, allowed_types) for elem in elems]
        else:
            raise EasyBuildError("Don't know how to combine value of type %s with allowed types of type %s",
                                 type(elems), type(allowed_types))
    elif isinstance(elems, dict):
        # allowed_types can be a tuple representation of a dict, or a flat list of types

        # try to convert to a dict, but ignore if it fails
        try:
            allowed_types = dict(allowed_types)
        except (ValueError, TypeError):
            pass

        if isinstance(allowed_types, (list, tuple)):
            elems_and_allowed_types = [(elem, allowed_types) for elem in elems.values()]
        elif isinstance(allowed_types, dict):
            elems_and_allowed_types = []
            for key, val in elems.items():
                if key in allowed_types:
                    elems_and_allowed_types.append((val, allowed_types[key]))
                else:
                    # if key has no known allowed types, use empty list of allowed types to yield False check result
                    elems_and_allowed_types.append((val, []))
        else:
            raise EasyBuildError("Unknown type of allowed types specification: %s", type(allowed_types))
    else:
        raise EasyBuildError("Don't know how to check element types for value of type %s: %s", type(elems), elems)

    # check whether all element types are allowed types
    res = True
    for elem, allowed_types_elem in elems_and_allowed_types:
        res &= any(is_value_of_type(elem, t) for t in allowed_types_elem)

    return res


def check_key_types(val, allowed_types):
    """Check whether type of keys for specific dict value are as expected."""
    if isinstance(val, dict):
        res = True
        for key in val.keys():
            res &= any(is_value_of_type(key, t) for t in allowed_types)
    else:
        _log.debug("Specified value %s (type: %s) is not a dict, so key types check failed", val, type(val))
        res = False

    return res


def check_known_keys(val, allowed_keys):
    """Check whether all keys for specified dict value are known keys."""
    if isinstance(val, dict):
        res = all(key in allowed_keys for key in val.keys())
    else:
        _log.debug("Specified value %s (type: %s) is not a dict, so known keys check failed", val, type(val))
        res = False
    return res


def check_required_keys(val, required_keys):
    """Check whether all required keys are present in the specified dict value."""
    if isinstance(val, dict):
        keys = val.keys()
        res = all(key in keys for key in required_keys)
    else:
        _log.debug("Specified value %s (type: %s) is not a dict, so known keys check failed", val, type(val))
        res = False
    return res


def is_value_of_type(value, expected_type):
    """
    Check whether specified value matches a particular very specific (non-trivial) type,
    which is specified by means of a 2-tuple: (parent type, tuple with additional type requirements).

    :param value: value to check the type of
    :param expected_type: type of value to check against
    """
    type_ok = False

    if expected_type in EASY_TYPES:
        # easy types can be checked using isinstance
        type_ok = isinstance(value, expected_type)

    elif expected_type in CHECKABLE_TYPES:
        # more complex types need to be checked differently, through helper functions for extra type requirements
        parent_type = expected_type[0]
        extra_reqs = dict(expected_type[1])

        # first step: check parent type
        type_ok = isinstance(value, parent_type)
        if type_ok:
            _log.debug("Parent type of value %s matches %s, going in...", value, parent_type)
            # second step: check additional type requirements
            extra_req_checkers = {
                'elem_types': lambda val: check_element_types(val, extra_reqs['elem_types']),
            }
            if parent_type == dict:
                extra_req_checkers.update({
                    'key_types': lambda val: check_key_types(val, extra_reqs['key_types']),
                    'opt_keys': lambda val: check_known_keys(val, extra_reqs['opt_keys'] + extra_reqs['req_keys']),
                    'req_keys': lambda val: check_required_keys(val, extra_reqs['req_keys']),
                })

            for er_key in extra_reqs:
                if er_key in extra_req_checkers:
                    check_ok = extra_req_checkers[er_key](value)
                    msg = ('FAILED', 'passed')[check_ok]
                    type_ok &= check_ok
                    _log.debug("Check for %s requirement (%s) %s for %s", er_key, extra_reqs[er_key], msg, value)
                else:
                    raise EasyBuildError("Unknown type requirement specified: %s", er_key)

            msg = ('FAILED', 'passed')[type_ok]
            _log.debug("Non-trivial value type checking of easyconfig value '%s': %s", value, msg)

        else:
            _log.debug("Parent type of value %s doesn't match %s: %s", value, parent_type, type(value))

    else:
        raise EasyBuildError("Don't know how to check whether specified value is of type %s", expected_type)

    return type_ok


def check_type_of_param_value(key, val, auto_convert=False):
    """
    Check value type of specified easyconfig parameter.

    :param key: name of easyconfig parameter
    :param val: easyconfig parameter value, of which type should be checked
    :param auto_convert: try to automatically convert to expected value type if required
    """
    type_ok, newval = False, None
    expected_type = PARAMETER_TYPES.get(key)

    # check value type
    if expected_type is None:
        _log.debug("No type specified for easyconfig parameter '%s', so skipping type check.", key)
        type_ok = True

    else:
        type_ok = is_value_of_type(val, expected_type)

    # determine return value, attempt type conversion if needed/requested
    if type_ok:
        _log.debug("Value type check passed for %s parameter value: %s", key, val)
        newval = val
    elif auto_convert:
        _log.debug("Value type check for %s parameter value failed, going to try to automatically convert to %s",
                   key, expected_type)
        # convert_value_type will raise an error if the conversion fails
        newval = convert_value_type(val, expected_type)
        type_ok = True
    else:
        _log.debug("Value type check for %s parameter value failed, auto-conversion of type not enabled", key)

    return type_ok, newval


def convert_value_type(val, typ):
    """
    Try to convert type of provided value to specific type.

    :param val: value to convert type of
    :param typ: target type
    """
    res = None

    if typ in EASY_TYPES and isinstance(val, typ):
        _log.debug("Value %s is already of specified target type %s, no conversion needed", val, typ)
        res = val

    elif typ in CHECKABLE_TYPES and is_value_of_type(val, typ):
        _log.debug("Value %s is already of specified non-trivial target type %s, no conversion needed", val, typ)
        res = val

    elif typ in TYPE_CONVERSION_FUNCTIONS:
        func = TYPE_CONVERSION_FUNCTIONS[typ]
        _log.debug("Trying to convert value %s (type: %s) to %s using %s", val, type(val), typ, func)
        try:
            res = func(val)
            _log.debug("Type conversion seems to have worked, new type: %s", type(res))
        except Exception as err:
            raise EasyBuildError("Converting type of %s (%s) to %s using %s failed: %s", val, type(val), typ, func, err)

        if not isinstance(res, typ):
            raise EasyBuildError("Converting value %s to type %s didn't work as expected: got %s", val, typ, type(res))

    else:
        raise EasyBuildError("No conversion function available (yet) for target type %s", typ)

    return res


def to_toolchain_dict(spec):
    """
    Convert a comma-separated string or 2/3-element list of strings to a dictionary with name/version keys, and
    optionally a hidden key. If the specified value is a dict already, the keys are checked to be only
    name/version/hidden.

    For example: "intel, 2015a" => {'name': 'intel', 'version': '2015a'}
                 "foss, 2016a, True" => {'name': 'foss', 'version': '2016a', 'hidden': True}

    :param spec: a comma-separated string with two or three values, or a 2/3-element list of strings, or a dict
    """
    # check if spec is a string or a list of two values; else, it can not be converted
    if isinstance(spec, str):
        spec = spec.split(',')

    if isinstance(spec, (list, tuple)):
        # 2-element list
        if len(spec) == 2:
            res = {'name': spec[0].strip(), 'version': spec[1].strip()}
        # 3-element list
        elif len(spec) == 3:
            hidden = spec[2].strip().lower()
            if hidden in {'yes', 'true', 't', 'y', '1', 'on'}:
                hidden = True
            elif hidden in {'no', 'false', 'f', 'n', '0', 'off'}:
                hidden = False
            else:
                raise EasyBuildError("Invalid truth value %s", hidden)
            res = {'name': spec[0].strip(), 'version': spec[1].strip(), 'hidden': hidden}
        else:
            raise EasyBuildError("Can not convert list %s to toolchain dict. Expected 2 or 3 elements", spec)

    elif isinstance(spec, dict):
        # already a dict, check keys
        sorted_keys = sorted(spec.keys())
        if sorted_keys == ['name', 'version'] or sorted_keys == ['hidden', 'name', 'version']:
            res = spec
        else:
            raise EasyBuildError("Incorrect set of keys in provided dictionary, should be only name/version/hidden: %s",
                                 spec)

    else:
        raise EasyBuildError("Conversion of %s (type %s) to toolchain dict is not supported", spec, type(spec))

    return res


def to_name_version_dict(spec):
    """No longer supported, replaced by to_toolchain_dict."""
    _log.nosupport("to_name_version_dict; use to_toolchain_dict instead.", '3.0')


def to_list_of_strings(value):
    """
    Convert specified value to a list of strings, if possible.

    Supported: single string value, tuple of string values.
    """
    res = None

    # if value is already of correct type, we don't need to change anything
    if isinstance(value, list) and all(isinstance(s, str) for s in value):
        res = value
    elif isinstance(value, str):
        res = [value]
    elif isinstance(value, tuple) and all(isinstance(s, str) for s in value):
        res = list(value)
    else:
        raise EasyBuildError("Don't know how to convert provided value to a list of strings: %s", value)

    return res


def to_list_of_strings_and_tuples(spec):
    """
    Convert a 'list of lists and strings' to a 'list of tuples and strings'

    Example:
        ['foo', ['bar', 'baz']]
        to
        ['foo', ('bar', 'baz')]
    """
    str_tup_list = []

    if not isinstance(spec, (list, tuple)):
        raise EasyBuildError("Expected value to be a list, found %s (%s)", spec, type(spec))

    for elem in spec:
        if isinstance(elem, (str, tuple)):
            str_tup_list.append(elem)
        elif isinstance(elem, list):
            str_tup_list.append(tuple(elem))
        else:
            raise EasyBuildError("Expected elements to be of type string, tuple or list, got %s (%s)", elem, type(elem))

    return str_tup_list


def to_list_of_strings_and_tuples_and_dicts(spec):
    """
    Convert a 'list of dicts and tuples/lists and strings' to a 'list of dicts and tuples and strings'

    Example:
        ['foo', ['bar', 'baz']]
        to
        ['foo', ('bar', 'baz')]
    """
    str_tup_list = []

    if not isinstance(spec, (list, tuple)):
        raise EasyBuildError("Expected value to be a list, found %s (%s)", spec, type(spec))

    for elem in spec:
        if isinstance(elem, (str, tuple, dict)):
            str_tup_list.append(elem)
        elif isinstance(elem, list):
            str_tup_list.append(tuple(elem))
        else:
            raise EasyBuildError("Expected elements to be of type string, tuple, dict or list, got %s (%s)",
                                 elem, type(elem))

    return str_tup_list


def to_sanity_check_paths_entry(spec):
    """
    Convert a 'list of lists and strings' to a 'list of tuples and strings' while allowing dicts of lists or strings

    Example:
        ['foo', ['bar', 'baz'], {'f42': ['a', 'b']}]
        to
        ['foo', ('bar', 'baz'), {'f42': ('a', 'b')}]
    """
    result = []

    if not isinstance(spec, (list, tuple)):
        raise EasyBuildError("Expected value to be a list, found %s (%s)", spec, type(spec))

    for elem in spec:
        if isinstance(elem, (str, tuple)):
            result.append(elem)
        elif isinstance(elem, list):
            result.append(tuple(elem))
        elif isinstance(elem, dict):
            for key, value in elem.items():
                if not isinstance(key, str):
                    raise EasyBuildError("Expected keys to be of type string, got %s (%s)", key, type(key))
                elif isinstance(value, list):
                    elem[key] = tuple(value)
                elif not isinstance(value, (str, tuple)):
                    raise EasyBuildError("Expected elements to be of type string, tuple or list, got %s (%s)",
                                         value, type(value))
            result.append(elem)
        else:
            raise EasyBuildError("Expected elements to be of type string, tuple/list or dict, got %s (%s)",
                                 elem, type(elem))

    return result


def to_sanity_check_paths_dict(spec):
    """
    Convert a sanity_check_paths dict as received by yaml (a dict with list values that contain either lists or strings)

    Example:
        {'files': ['file1', ['file2a', 'file2b]], 'dirs': ['foo/bar']}
        to
        {'files': ['file1', ('file2a', 'file2b')], 'dirs': ['foo/bar']}
    """
    if not isinstance(spec, dict):
        raise EasyBuildError("Expected value to be a dict, found %s (%s)", spec, type(spec))

    sanity_check_dict = {}
    for key in spec:
        sanity_check_dict[key] = to_sanity_check_paths_entry(spec[key])
    return sanity_check_dict


# this uses to_toolchain, so it needs to be at the bottom of the module
def to_dependency(dep):
    """
    Convert a dependency specification to a dependency dict with name/version/versionsuffix/toolchain keys.

    Example:
        {'foo': '1.2.3', 'toolchain': 'GCC, 4.8.2'}
        to
        {'name': 'foo', 'version': '1.2.3', 'toolchain': {'name': 'GCC', 'version': '4.8.2'}}

    or
        {'name': 'fftw/3.3.4.1', 'external_module': True}
        to
        {'name': 'fftw/3.3.4.1', 'external_module': True, 'version': None}
    """
    # deal with dependencies coming for .eb easyconfig, typically in tuple format:
    #   (name, version[, versionsuffix[, toolchain]])
    if isinstance(dep, dict):
        depspec = {}

        if dep.get('external_module', False):
            expected_keys = ['external_module', 'name']
            if sorted(dep.keys()) == expected_keys:
                depspec.update({
                    'external_module': True,
                    'full_mod_name': dep['name'],
                    'name': None,
                    'short_mod_name': dep['name'],
                    'version': None,
                })
            else:
                raise EasyBuildError("Unexpected format for dependency marked as external module: %s", dep)

        else:
            dep_keys = list(dep.keys())

            # need to handle name/version keys first, to avoid relying on order in which keys are processed...
            for key in ['name', 'version']:
                if key in dep:
                    depspec[key] = str(dep[key])
                    dep_keys.remove(key)

            for key in dep_keys:
                if key == 'versionsuffix':
                    depspec[key] = str(dep[key])
                elif key == 'toolchain':
                    depspec['toolchain'] = to_toolchain_dict(dep[key])
                elif not ('name' in depspec and 'version' in depspec):
                    depspec.update({'name': key, 'version': str(dep[key])})
                else:
                    raise EasyBuildError("Found unexpected (key, value) pair: %s, %s", key, dep[key])

            if not ('name' in depspec and 'version' in depspec):
                raise EasyBuildError("Can not parse dependency without name and version: %s", dep)

    else:
        # pass down value untouched, let EasyConfig._parse_dependency handle it
        depspec = dep
        if isinstance(dep, (tuple, list)):
            _log.debug("Passing down dependency value of type %s without touching it: %s", type(dep), dep)
        else:
            _log.warning("Unknown type of value in to_dependency %s; passing value down as is: %s", type(dep), dep)

    return depspec


def to_dependencies(dep_list):
    """
    Convert a list of dependencies obtained from parsing a .yeb easyconfig
    to a list of dependencies in the correct format
    """
    return [to_dependency(dep) for dep in dep_list]


def _to_checksum(checksum, list_level=0, allow_dict=True):
    """Ensure the correct element type for each checksum in the checksum list"""
    # each entry can be:
    # * None (indicates no checksum)
    # * a string (SHA256 checksum)
    # * a list or tuple with 2 elements: checksum type + checksum value
    # * a list or tuple of checksums (i.e. multiple checksums for a single file)
    # * a dict (filename to checksum mapping)
    if checksum is None or isinstance(checksum, str):
        return checksum
    elif isinstance(checksum, (list, tuple)):
        if len(checksum) == 2 and isinstance(checksum[0], str) and isinstance(checksum[1], (str, int)):
            # 2 elements so either:
            #  - a checksum tuple (2nd element string or int)
            #  - 2 alternative checksums (tuple)
            #  - 2 checksums that must each match (list)
            # --> Convert to tuple only if we can exclude the 3rd case
            if not isinstance(checksum[1], str) or list_level > 0:
                return tuple(checksum)
            else:
                return checksum
        elif list_level < 2:
            # Alternative checksums or multiple checksums for a single file
            # Allowed to nest (at most) 2 times, e.g. [[[type, value]]] == [[(type, value)]]
            # None is not allowed here
            if any(x is None for x in checksum):
                raise ValueError('Unexpected None in ' + str(checksum))
            if isinstance(checksum, tuple) or list_level > 0:
                # When we already are in a tuple no further recursion is allowed -> set list_level very high
                return tuple(_to_checksum(x, list_level=99, allow_dict=allow_dict) for x in checksum)
            else:
                return list(_to_checksum(x, list_level=list_level+1, allow_dict=allow_dict) for x in checksum)
    elif isinstance(checksum, dict) and allow_dict:
        return {key: _to_checksum(value, allow_dict=False) for key, value in checksum.items()}

    # Not returned -> Wrong type/format
    raise ValueError('Unexpected type of "%s": %s' % (type(checksum), str(checksum)))


def to_checksums(checksums):
    """Ensure correct element types for list of checksums: convert list elements to tuples."""
    try:
        return [_to_checksum(checksum) for checksum in checksums]
    except ValueError as e:
        raise EasyBuildError('Invalid checksums: %s\n\tError: %s', checksums, e)


def ensure_iterable_license_specs(specs):
    """
    Ensures that the provided license file/server specifications are of correct type and converts
    them to a list.  The input can either be None, a string, or a list/tuple of strings.

    :param specs: License file/server specifications as provided via `license_file` easyconfig parameter
    """
    if specs is None:
        license_specs = [None]
    elif isinstance(specs, str):
        license_specs = [specs]
    elif isinstance(specs, (list, tuple)) and all(isinstance(x, str) for x in specs):
        license_specs = list(specs)
    else:
        msg = "Unsupported type %s for easyconfig parameter 'license_file'! " % type(specs)
        msg += "Can either be None, a string, or a tuple/list of strings."
        raise EasyBuildError(msg)

    return license_specs


# these constants use functions defined in this module, so they needs to be at the bottom of the module
# specific type: dict with only name/version as keys with string values, and optionally a hidden key with bool value
# additional type requirements are specified as tuple of tuples rather than a dict, since this needs to be hashable
TOOLCHAIN_DICT = (dict, as_hashable({
    'elem_types': {
        'hidden': [bool],
        'name': [str],
        'version': [str],
    },
    'opt_keys': ['hidden'],
    'req_keys': ['name', 'version'],
}))
DEPENDENCY_DICT = (dict, as_hashable({
    'elem_types': {
        'full_mod_name': [str],
        'name': [str],
        'short_mod_name': [str],
        'toolchain': [TOOLCHAIN_DICT],
        'version': [str],
        'versionsuffix': [str],
    },
    'opt_keys': ['full_mod_name', 'short_mod_name', 'toolchain', 'versionsuffix'],
    'req_keys': ['name', 'version'],
}))
DEPENDENCIES = (list, as_hashable({'elem_types': [DEPENDENCY_DICT]}))

TUPLE_OF_STRINGS = (tuple, as_hashable({'elem_types': [str]}))
LIST_OF_STRINGS = (list, as_hashable({'elem_types': [str]}))
STRING_OR_TUPLE_LIST = (list, as_hashable({'elem_types': [str, TUPLE_OF_STRINGS]}))
STRING_DICT = (dict, as_hashable(
    {
        'elem_types': [str],
        'key_types': [str],
    }
))
STRING_OR_TUPLE_DICT = (dict, as_hashable(
    {
        'elem_types': [str],
        'key_types': [str, TUPLE_OF_STRINGS],
    }
))
STRING_OR_TUPLE_OR_DICT_LIST = (list, as_hashable({'elem_types': [str, TUPLE_OF_STRINGS, STRING_DICT]}))
SANITY_CHECK_PATHS_ENTRY = (list, as_hashable({'elem_types': [str, TUPLE_OF_STRINGS, STRING_OR_TUPLE_DICT]}))
SANITY_CHECK_PATHS_DICT = (dict, as_hashable({
    'elem_types': {
        SANITY_CHECK_PATHS_FILES: [SANITY_CHECK_PATHS_ENTRY],
        SANITY_CHECK_PATHS_DIRS: [SANITY_CHECK_PATHS_ENTRY],
    },
    'opt_keys': [],
    'req_keys': [SANITY_CHECK_PATHS_FILES, SANITY_CHECK_PATHS_DIRS],
}))
# checksums is a list of checksums, one entry per file (source/patch)
# each entry can be:
# None
# a single checksum value (string)
# a single checksum value of a specified type (2-tuple, 1st element is checksum type, 2nd element is checksum)
# a list of checksums (of different types, perhaps different formats), which should *all* be valid
# a tuple of checksums (of different types, perhaps different formats), where one should be valid
# a dictionary with a mapping from filename to checksum (None, value, type&value, alternatives)

# Type & value, value may be an int for type "size"
# This is a bit too permissive as it allows the first element to be an int and doesn't restrict the number of elements
CHECKSUM_AND_TYPE = (tuple, as_hashable({'elem_types': [str, int]}))
CHECKSUM_LIST = (list, as_hashable({'elem_types': [str, CHECKSUM_AND_TYPE]}))
CHECKSUM_TUPLE = (tuple, as_hashable({'elem_types': [str, CHECKSUM_AND_TYPE]}))
CHECKSUM_DICT = (dict, as_hashable(
    {
        'elem_types': [type(None), str, CHECKSUM_AND_TYPE, CHECKSUM_TUPLE, CHECKSUM_LIST],
        'key_types': [str],
    }
))
# At the top-level we allow tuples/lists containing a dict
CHECKSUM_LIST_W_DICT = (list, as_hashable({'elem_types': [str, CHECKSUM_AND_TYPE, CHECKSUM_DICT]}))
CHECKSUM_TUPLE_W_DICT = (tuple, as_hashable({'elem_types': [str, CHECKSUM_AND_TYPE, CHECKSUM_DICT]}))

CHECKSUMS = (list, as_hashable({'elem_types': [type(None), str, CHECKSUM_AND_TYPE,
                                               CHECKSUM_LIST_W_DICT, CHECKSUM_TUPLE_W_DICT, CHECKSUM_DICT]}))

CHECKABLE_TYPES = [CHECKSUM_AND_TYPE, CHECKSUM_LIST, CHECKSUM_TUPLE,
                   CHECKSUM_LIST_W_DICT, CHECKSUM_TUPLE_W_DICT, CHECKSUM_DICT, CHECKSUMS,
                   DEPENDENCIES, DEPENDENCY_DICT, LIST_OF_STRINGS,
                   SANITY_CHECK_PATHS_DICT, SANITY_CHECK_PATHS_ENTRY, STRING_DICT, STRING_OR_TUPLE_LIST,
                   STRING_OR_TUPLE_DICT, STRING_OR_TUPLE_OR_DICT_LIST, TOOLCHAIN_DICT, TUPLE_OF_STRINGS]

# easy types, that can be verified with isinstance
EASY_TYPES = [str, bool, dict, int, list, str, tuple, type(None)]

# type checking is skipped for easyconfig parameters names not listed in PARAMETER_TYPES
PARAMETER_TYPES = {
    'checksums': CHECKSUMS,
    'docurls': LIST_OF_STRINGS,
    'name': str,
    'osdependencies': STRING_OR_TUPLE_LIST,
    'patches': STRING_OR_TUPLE_OR_DICT_LIST,
    'sanity_check_paths': SANITY_CHECK_PATHS_DICT,
    'toolchain': TOOLCHAIN_DICT,
    'version': str,
}
# add all dependency types as dependencies
for dep in DEPENDENCY_PARAMETERS:
    PARAMETER_TYPES[dep] = DEPENDENCIES

TYPE_CONVERSION_FUNCTIONS = {
    str: str,
    float: float,
    int: int,
    str: str,
    CHECKSUMS: to_checksums,
    DEPENDENCIES: to_dependencies,
    LIST_OF_STRINGS: to_list_of_strings,
    TOOLCHAIN_DICT: to_toolchain_dict,
    SANITY_CHECK_PATHS_DICT: to_sanity_check_paths_dict,
    STRING_OR_TUPLE_LIST: to_list_of_strings_and_tuples,
    STRING_OR_TUPLE_OR_DICT_LIST: to_list_of_strings_and_tuples_and_dicts,
}
