"""Address lines split into the fields the Census geocoder expects."""

from nextvisit.geocode import _direction_ok, _read_matches, parse_address, tidy_address


def test_comma_separated_address_keeps_street_city_and_zip() -> None:
    assert parse_address(
        "14507 BOTHELL WAY NE, SHORELINE, WA 98155",
        default_state="WA",
    ) == ("14507 BOTHELL WAY NE", "SHORELINE", "WA", "98155")


def test_manhattan_is_sent_as_new_york() -> None:
    assert parse_address(
        "1802 65TH ST TRANSVERSE, Manhattan, NY",
        default_state="NY",
    ) == ("1802 65TH ST TRANSVERSE", "New York", "NY", "")


def test_parenthetical_note_is_removed() -> None:
    assert parse_address(
        "5516 S Maplewood (2532W) AVE, chicago, IL 60629",
        default_state="IL",
    ) == ("5516 S Maplewood AVE", "chicago", "IL", "60629")


def test_city_stuck_to_the_street_is_split_off() -> None:
    assert parse_address(
        "619 N Interstate 35 Austin, TX 78702-3202",
        default_state="TX",
    ) == ("619 N Interstate 35", "Austin", "TX", "78702")


def test_slash_in_the_city_is_ignored() -> None:
    assert parse_address(
        "300 CHELSEA ST, CHARLESTOWN/, MA 02129",
        default_state="MA",
    ) == ("300 CHELSEA ST", "CHARLESTOWN", "MA", "02129")


def test_tidy_strips_a_unit_and_a_repeated_suffix() -> None:
    assert tidy_address(("18000 INTERNATIONAL BLVD BLVD S", "SEATAC", "WA", "98188")) == (
        "18000 INTERNATIONAL BLVD S",
        "SEATAC",
        "WA",
        "98188",
    )
    assert tidy_address(("2217 W CRYSTAL ST APT 2", "CHICAGO", "IL", "60622"))[0] == "2217 W CRYSTAL ST"


def test_tidy_uses_the_first_number_of_a_range() -> None:
    assert tidy_address(("1802-1810 E 35TH ST", "CHICAGO", "IL", "60609"))[0] == "1802 E 35TH ST"


def test_tidy_sends_a_boston_neighborhood_as_boston() -> None:
    assert tidy_address(("1095 COMMONWEALTH AV", "ALLSTON", "MA", "02134")) == (
        "1095 COMMONWEALTH AVE",
        "Boston",
        "MA",
        "02134",
    )
    assert tidy_address(("1 MAIN ST", "CHELSEA", "MA", "02150"))[1] == "CHELSEA"


def test_a_flipped_street_direction_is_rejected() -> None:
    assert _direction_ok("1802 E 35TH ST", "1802 W 35TH ST, CHICAGO, IL, 60609") is False
    assert _direction_ok("300 CHELSEA ST", "300 CHELSEA ST, BOSTON, MA, 02128") is True


def test_a_tie_without_coordinates_is_split_out_of_the_matches() -> None:
    body = (
        '"0","1100 Broadway, Seattle, WA, 98122","Tie"\n'
        '"1","300 CHELSEA ST, Boston, MA, 02129","Match","Non_Exact",'
        '"300 CHELSEA ST, BOSTON, MA, 02128","-71.03093,42.37676","1","L"\n'
        '"2","1802 E 35TH ST, CHICAGO, IL, 60609","Match","Non_Exact",'
        '"1802 W 35TH ST, CHICAGO, IL, 60609","-87.67057,41.83050","1","R"\n'
    )
    found, ties = _read_matches(body)
    assert ties == [0]
    assert found[1] == (42.37676, -71.03093)
    assert 2 not in found
