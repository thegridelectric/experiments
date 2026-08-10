#!/usr/bin/env python3
"""Syntactic bijection between the sema formats spaceheat.name and
left.right.dot. The two share an identical segment grammar (first
segment begins with a lowercase letter, later segments are [a-z0-9]+)
and differ only in separator (dash vs dot), so separator substitution
maps one onto the other. The correspondence is exactly bijective
between spaceheat.name and the length-<=64 sublanguage of
left.right.dot (spaceheat.name carries a 64-char maximum;
left.right.dot is unbounded). Both directions validate against the
sema property formats and raise on any value outside them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pydantic import TypeAdapter  # noqa: E402

from gwexp.sema.property_format import LeftRightDot, SpaceheatName  # noqa: E402

_SPACEHEAT = TypeAdapter(SpaceheatName)
_LRD = TypeAdapter(LeftRightDot)

def spaceheat_name_to_lrd_token(name: str) -> LeftRightDot:
    """SpaceheatName -> LeftRightDot (dashes -> dots). Total on valid
    SpaceheatNames; raises otherwise."""
    _SPACEHEAT.validate_python(name)
    return _LRD.validate_python(name.replace("-", "."))


def lrd_token_to_spaceheat_name(token: str) -> SpaceheatName:
    """LeftRightDot -> SpaceheatName (dots -> dashes). Defined on the
    length-<=64 sublanguage of LeftRightDot; raises outside it."""
    _LRD.validate_python(token)
    return _SPACEHEAT.validate_python(token.replace(".", "-"))


def validate_lrd(value: str) -> LeftRightDot:
    """Assert a value already IS LeftRightDot (e.g. a GNode alias used
    directly as a filename token, no conversion involved)."""
    return _LRD.validate_python(value)
