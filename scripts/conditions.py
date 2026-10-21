"""Evaluate rule conditions against a post's facts.

A condition is a check, [fact, op, value], or a mapping with one key, all or
any, holding a list of conditions. A value written as $name is the fact of
that name. A check is True, False, or None when a fact it reads is unknown,
and all/any combine the three.
"""
import operator

OPS = {
    "==": operator.eq, "!=": operator.ne,
    "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
}


class ConditionError(ValueError):
    pass


def validate(cond, where, known=None):
    if isinstance(cond, list):
        if len(cond) != 3 or not isinstance(cond[0], str) or cond[1] not in OPS:
            raise ConditionError(f"{where}: a check is [fact, op, value] with op one of {' '.join(OPS)}")
        for name in (cond[0], _ref(cond[2])):
            if known is not None and name is not None and name not in known:
                raise ConditionError(f"{where}: unknown fact {name!r}")
        return
    if isinstance(cond, dict) and len(cond) == 1 and next(iter(cond)) in ("all", "any"):
        key, parts = next(iter(cond.items()))
        if not isinstance(parts, list) or not parts:
            raise ConditionError(f"{where}: {key} needs a list of conditions")
        for k, part in enumerate(parts):
            validate(part, f"{where}.{key}[{k}]", known)
        return
    raise ConditionError(f"{where}: expected [fact, op, value], or all/any with a list")


def evaluate(cond, facts):
    """(True, False or None, and the checks read as 'fact value op target')."""
    if isinstance(cond, list):
        name, op, target = cond
        ref = _ref(target)
        value = facts.get(name)
        if ref:
            target = facts.get(ref)
        if value is None or target is None:
            return None, [f"{name if value is None else ref} unknown"]
        try:
            ok = OPS[op](value, target)
        except TypeError:
            return None, [f"{name} {value!r} can't be compared with {target!r}"]
        return ok, [f"{name} {_show(value)} {op} {_show(target)}"]
    key, parts = next(iter(cond.items()))
    results = [evaluate(part, facts) for part in parts]
    values = [result for result, _ in results]
    details = [d for _, ds in results for d in ds]
    decisive = key == "any"
    if decisive in values:
        return decisive, details
    if None in values:
        return None, details
    return not decisive, details


def _ref(target):
    if isinstance(target, str) and target.startswith("$") and len(target) > 1:
        return target[1:]
    return None


def _show(value):
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(round(value, 2))
    return str(value)
