"""Deterministic human-readable rendering of the machine-readable diagnosis."""


def diagnosis_markdown(report):
    lines = ['# Automated performance diagnosis', '',
             'Evidence-based triage, not a measured speedup or certified critical path.', '',
             '## Findings', '']
    for entry in report['findings']:
        lines += [f"### {entry['code']} ({entry['severity']}; {entry['confidence']} confidence)", '',
                  entry['observation'], '', f"**Next experiment:** {entry['next_experiment']}", '']
    lines += ['## Evidence sources', '']
    for key in report['sources']:
        lines.append(f'- `{key}`')
    lines += ['', '## Limitations', '']
    for item in dict.fromkeys(report['limitations']):
        lines.append(f'- {item}')
    lines.append('')
    return '\n'.join(lines)
