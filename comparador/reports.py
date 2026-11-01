"""Local reports in the currently selected application language."""
from pathlib import Path
import csv
import datetime
import html
from .i18n import tr, language
from .models import duration_text

HEADERS = ["Path", "Folder", "Status", "Bytes", "Duration", "Resolution", "SHA-256", "Exact matches", "Visual candidates", "Visual details", "Error", "Comparison notes"]


def report_rows(result):
    for key, record in result.files.items():
        visual = result.visual_peers(key)
        details = []
        for peer, match in visual:
            spans = match.spans if match.a == key else [[s[2],s[3],s[0],s[1]] for s in match.spans]
            segments = ". ".join(f"{duration_text(s[0])} to {duration_text(s[1])} / {duration_text(s[2])} to {duration_text(s[3])}" for s in spans)
            detail = tr("Visual {similarity}%, coverage {coverage}%. {segments}", similarity=f"{match.similarity:.1f}", coverage=f"{match.coverage:.1f}", segments=segments)
            if match.estimated:
                detail += ' ' + tr('Coverage and ranges estimated from samples.')
            details.append(peer.path + "\n" + detail)
        yield [record.path, tr("Primary") if record.root == "primary" else tr("Secondary"), tr(result.display_status(key)), record.size,
               duration_text(record.metadata.get("duration")), f"{record.metadata.get('width',0)} x {record.metadata.get('height',0)}" if record.metadata else "",
               record.digest, "\n".join(p.path for p in result.exact_peers(key)), "\n".join(p.path for p,_ in visual), "\n".join(details),
               "\n".join(x for x in (record.error, record.video_error) if x), result.comparison_note(key)]


def csv_safe(value):
    value = str(value)
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


def export_csv(result, path):
    with open(path,"w",encoding="utf-8-sig",newline="") as output:
        writer = csv.writer(output,delimiter=";")
        writer.writerow(["Video Duplicate Finder", datetime.datetime.fromtimestamp(result.created).isoformat(timespec="seconds")])
        writer.writerow([tr("Primary"),str(result.options.primary),tr("Secondary"),str(result.options.secondary or "")])
        writer.writerow([tr("Profile"),result.options.video_profile,tr("Minimum visual similarity"),result.options.similarity,tr("Minimum content coverage"),result.options.coverage])
        if result.options.video_profile in ('segments', 'segments_fast'):
            writer.writerow([tr('Segment matching allows internal cuts and counts shared content against the longer video.')])
        if result.options.video_profile == 'segments_fast':
            writer.writerow([tr('Quick segment coverage and ranges are estimated from at most 160 captures. Unmatched sections may be missed.')])
        writer.writerow([tr("Complete scan"),result.exact_complete and (not result.options.similar or result.video_complete),tr("Canceled"),result.cancelled])
        for error in result.errors:
            writer.writerow([tr("Error"),csv_safe(error)])
        writer.writerow([tr(h) for h in HEADERS])
        writer.writerows([[csv_safe(value) for value in row] for row in report_rows(result)])


def export_html(result,path):
    esc = lambda value: html.escape(str(value))
    rows = "\n".join("<tr>"+"".join(f"<td>{esc(value)}</td>" for value in row)+"</tr>" for row in report_rows(result))
    errors = "".join(f"<li>{esc(error)}</li>" for error in result.errors)
    text = f'''<!doctype html><html lang="{language()}"><meta charset="utf-8"><title>Video Duplicate Finder</title>
<style>body{{font:14px 'Segoe UI',sans-serif;color:#203238;background:#f5f6f3;margin:28px}}table{{border-collapse:collapse;width:100%;background:white}}th,td{{text-align:left;padding:12px;border-bottom:1px solid #cad6ce;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}}th{{background:#e9eeea}}</style>
<h1>Video Duplicate Finder</h1><p><b>{esc(tr('Primary'))}:</b> {esc(result.options.primary)}<br><b>{esc(tr('Secondary'))}:</b> {esc(result.options.secondary or tr('No secondary folder'))}</p>
<p>{esc(tr('Profile'))}: {esc(result.options.video_profile)}. {esc(tr('Minimum visual similarity'))}: {result.options.similarity}%. {esc(tr('Minimum content coverage'))}: {result.options.coverage}%.</p>
<p>{esc(tr('Canceled'))}: {result.cancelled}. {esc(tr('Complete scan'))}: {result.exact_complete and (not result.options.similar or result.video_complete)}.</p>
<p>{esc(tr('Coverage is estimated from samples in quick mode. Audio is not compared.'))}</p>
<p>{esc(tr('Segment matching allows internal cuts and counts shared content against the longer video.')) if result.options.video_profile in ('segments', 'segments_fast') else ''}</p>
<p>{esc(tr('Quick segment coverage and ranges are estimated from at most 160 captures. Unmatched sections may be missed.')) if result.options.video_profile == 'segments_fast' else ''}</p><ul>{errors}</ul>
<table><thead><tr>{''.join(f'<th>{esc(tr(h))}</th>' for h in HEADERS)}</tr></thead><tbody>{rows}</tbody></table></html>'''
    Path(path).write_text(text,encoding="utf-8")
