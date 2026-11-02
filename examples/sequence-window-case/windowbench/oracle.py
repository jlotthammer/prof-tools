"""Straightforward independent reference for exact integer feature semantics."""
from .baseline import CHARGED, HYDROPHOBIC


def features(sequences):
    valid_counts, hydrophobic_counts, charge_sums = [], [], []
    for amino_acids, visible, radius in sequences:
        for center in range(len(amino_acids)):
            indices = (j for j in range(len(amino_acids)) if abs(j - center) <= radius and visible[j])
            neighborhood = [amino_acids[j] for j in indices]
            valid_counts.append(len(neighborhood))
            hydrophobic_counts.append(sum(aa in HYDROPHOBIC for aa in neighborhood))
            charge_sums.append(sum(CHARGED.get(aa, 0) for aa in neighborhood))
    return valid_counts, hydrophobic_counts, charge_sums
