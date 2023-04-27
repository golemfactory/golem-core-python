from typing import Any, Callable, Optional, Type, Union, get_args, get_origin


def match_type_union_aware(obj_type: Type, match_func: Callable[[Type], bool]) -> Optional[Any]:
    """Check if given obj_type matches match_func and return matched type.

    In case when obj_type is a Union (for e.g. result of Optional[...] makes Union[..., None]),
    match_func wil be run for Union arguments, first match will returned matched argument.
    """
    if match_func(obj_type):
        return obj_type

    if get_origin(obj_type) == Union:
        for union_obj_type in get_args(obj_type):
            if match_func(union_obj_type):
                return union_obj_type

    return None
