"""Plain armor prototype: rear shell + front bezel, no decoration."""
from projects.armor.params import Params
from projects.armor.part import ArmorPart

from projects.armor.models._armor_base import front_bezel, print_location_front, print_location_rear, rear_shell


def build(p: Params) -> dict[str, ArmorPart]:
    return {
        "rear": ArmorPart(rear_shell(p), print_location_rear(p)),
        "front": ArmorPart(front_bezel(p), print_location_front(p)),
    }
