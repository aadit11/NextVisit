"""One readable address line. Missing and placeholder parts are left out."""

_MISSING = {"", "n/a", "na", "none", "null", "0"}


def address_part(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if text.casefold() in _MISSING:
        return None
    return text


def street_line(building: object, street: object) -> str | None:
    """Join a building number and a street, skipping either side when it is blank."""
    number = address_part(building)
    name = address_part(street)
    if number and name:
        return f"{number} {name}"
    return name or number


def format_address(street: object, city: object = None, state: object = None, zip_code: object = None) -> str | None:
    """Street, city, then state and ZIP as the last piece."""
    if address_part(street) is None and address_part(city) is None:
        return None
    locality = " ".join(
        piece for piece in (address_part(state), address_part(zip_code)) if piece
    )
    pieces = [address_part(street), address_part(city), locality or None]
    kept: list[str] = []
    for piece in pieces:
        if piece and piece.casefold() not in {item.casefold() for item in kept}:
            kept.append(piece)
    if not kept:
        return None
    return ", ".join(kept)
