from collections import defaultdict

from pymatgen.analysis.structure_matcher import SpeciesComparator, StructureMatcher
from pymatgen.core import Structure


class StructureRegistry:
    """Equivalent cells, reorderings and supercells cannot earn extra credit.

    This registry checks duplication only, not worldwide or literature novelty.
    """

    def __init__(self):
        self.matcher = StructureMatcher(ltol=0.1, stol=0.15, angle_tol=3,
                                        primitive_cell=True, scale=False,
                                        attempt_supercell=True, comparator=SpeciesComparator())
        self.groups = defaultdict(list)

    def register(self, identifier: str, structure: Structure) -> str | None:
        key = structure.composition.fractional_composition
        for prior_id, prior_structure in self.groups[key]:
            if self.matcher.fit(prior_structure, structure):
                return prior_id
        self.groups[key].append((identifier, structure))
        return None
