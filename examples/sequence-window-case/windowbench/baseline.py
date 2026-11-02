"""Intentionally unoptimized CPU implementation: repeated neighborhood scanning."""

CHARGED = {1: 1, 3: -1, 6: 1, 8: -1, 14: 1}
HYDROPHOBIC = {0, 4, 7, 9, 10, 12, 17, 18}


def features(sequences):
    counts = []
    hydrophobic = []
    charges = []
    for residues, observed, radius in sequences:
        for i in range(len(residues)):
            low = max(0, i - radius)
            high = min(len(residues), i + radius + 1)
            count = 0
            hydrophobic_count = 0
            charge_sum = 0
            for j in range(low, high):
                if observed[j]:
                    aa = residues[j]
                    count += 1
                    if aa in HYDROPHOBIC:
                        hydrophobic_count += 1
                    charge_sum += CHARGED.get(aa, 0)
            counts.append(count)
            hydrophobic.append(hydrophobic_count)
            charges.append(charge_sum)
    return counts, hydrophobic, charges
