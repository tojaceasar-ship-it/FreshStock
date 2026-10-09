from decimal import Decimal, InvalidOperation


QUANTITY_STEP = Decimal("0.001")
DISCRETE_UNITS = {"szt", "opak", "karton"}


class QuantityValidationError(ValueError):
    pass


def quantity(value, *, allow_zero: bool = False) -> Decimal:
    """Return a finite quantity with at most three fractional digits."""
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QuantityValidationError("Ilość musi być liczbą") from exc
    if not result.is_finite():
        raise QuantityValidationError("Ilość musi być liczbą skończoną")
    if result < 0 or (result == 0 and not allow_zero):
        raise QuantityValidationError("Ilość musi być dodatnia" if not allow_zero else "Ilość nie może być ujemna")
    if result.as_tuple().exponent < -3:
        raise QuantityValidationError("Ilość może mieć maksymalnie 3 miejsca po przecinku")
    return result.quantize(QUANTITY_STEP)


def quantity_for_unit(value, unit, *, allow_zero: bool = False) -> Decimal:
    result = quantity(value, allow_zero=allow_zero)
    unit_value = getattr(unit, "value", unit)
    if unit_value in DISCRETE_UNITS and result != result.to_integral_value():
        raise QuantityValidationError(f"Jednostka {unit_value} wymaga ilości całkowitej")
    return result
