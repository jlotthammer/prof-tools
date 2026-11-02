"""Readonly analysis of Nsight Systems and ROCm rocpd SQLite files.

Only kernel dispatches are counted as GPU execution. Memory-copy engines are
not included in kernel busy time. Occupancy/SM active cannot be derived from
these intervals. Per-device interval union is not a critical-path analysis.
"""


def columns(conn, table):
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('view','table')")}


from .intervals import duration as union_duration


def identify(conn):
    names = tables(conn)
    if "CUPTI_ACTIVITY_KIND_KERNEL" in names:
        return "nvidia"
    if "kernels" in names or "kernel_dispatch" in names:
        return "amd"
    raise ValueError("unrecognized trace schema; inspect sqlite_master and supply adapter")


def marker_windows(conn, vendor, name):
    """Host marker spans used ONLY to select a diagnostic time window.

    Host ranges do not automatically enclose asynchronously launched GPU work;
    for precise GPU attribution use correlation IDs / GPU projection in a GUI.
    """
    names = tables(conn)
    windows = []
    if vendor == "nvidia" and "NVTX_EVENTS" in names:
        cs = columns(conn, "NVTX_EVENTS")
        if {"start", "end"} <= cs:
            if "text" in cs and "textId" in cs and "StringIds" in names:
                sql = "SELECT n.start,n.end,COALESCE(NULLIF(n.text,''),s.value) FROM NVTX_EVENTS n LEFT JOIN StringIds s ON n.textId=s.id WHERE n.end > n.start"
            elif "text" in cs:
                sql = "SELECT start,end,text FROM NVTX_EVENTS WHERE end > start"
            elif "textId" in cs and "StringIds" in names:
                sql = "SELECT n.start,n.end,s.value FROM NVTX_EVENTS n JOIN StringIds s ON n.textId=s.id WHERE n.end > n.start"
            else:
                raise ValueError("Nsight NVTX_EVENTS missing text and textId")
            windows = [(int(s), int(e)) for s, e, text in conn.execute(sql) if text == name]
    elif vendor == "amd" and "regions" in names:
        cs = columns(conn, "regions")
        start = next((k for k in ("start", "start_timestamp", "start_time") if k in cs), None)
        end = next((k for k in ("end", "end_timestamp", "end_time") if k in cs), None)
        duration = "duration" if "duration" in cs else None
        if "name" not in cs or not start or (not end and not duration):
            raise ValueError("rocpd regions view missing expected name/timing columns; inspect schema")
        cols = f'name,"{start}","{end}"' if end else f'name,"{start}","{duration}"'
        for title, s, e in conn.execute(f"SELECT {cols} FROM regions"):
            if title == name and s is not None and e is not None:
                finish = int(e) if end else int(s) + int(e)
                if finish > int(s):
                    windows.append((int(s), finish))
    if not windows:
        raise ValueError(f"marker {name!r} absent or schema lacks compatible range events")
    return sorted(windows)
