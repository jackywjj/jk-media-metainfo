#!/usr/bin/env python3
"""Local, allowlisted descriptive metadata editing. Never shell out through a shell."""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

BASE = pathlib.Path(__file__).resolve().parent
VERSION = '0.2.0'
MAX_FILES = 512
MIN_VERSIONS = {'python': (3, 10), 'Pillow': (10, 4), 'exiftool': (13, 0),
                'ffprobe': (6, 0), 'ffmpeg': (6, 0), 'mkvextract': (80, 0), 'mkvpropedit': (80, 0)}
KINDS = {'photo', 'ai_generated', 'illustration', 'mixed', 'non_person', 'unknown'}
SCOPES = {'real', 'fictional', 'mixed', 'none', 'unknown'}
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp', '.gif', '.heic', '.heif', '.avif'}
VIDEO_EXT = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.wmv', '.m4v'}
EMBED_IMAGE = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp', '.gif'}
# (ExifTool tag, value type). Custom fields use only the fixed local config.
FIELDS = {
    'title': ('XMP-dc:Title', 'text'),
    'description': ('XMP-dc:Description', 'text'),
    'creator': ('XMP-dc:Creator', 'list'),
    'editor': ('XMP-photoshop:CaptionWriter', 'text'),
    'contributors': ('XMP-dc:Contributor', 'list'),
    'keywords': ('XMP-dc:Subject', 'list'),
    'source_url': ('XMP-dc:Source', 'url'),
    'original_image_url': ('XMP-jkmedia:OriginalImageURL', 'url'),
    'reference_urls': ('XMP-jkmedia:ReferenceURLs', 'urls'),
    'creator_url': ('XMP-iptcCore:CreatorWorkURL', 'url'),
    'license_url': ('XMP-xmpRights:WebStatement', 'url'),
    'usage_terms': ('XMP-xmpRights:UsageTerms', 'text'),
    'rights': ('XMP-dc:Rights', 'text'),
    'credit': ('XMP-photoshop:Credit', 'text'),
    'project': ('XMP-jkmedia:Project', 'text'),
    'series': ('XMP-jkmedia:Series', 'text'),
    'asset_id': ('XMP-jkmedia:AssetID', 'text'),
    'page': ('XMP-jkmedia:Page', 'text'),
    'version': ('XMP-jkmedia:Version', 'text'),
    'rating': ('XMP-xmp:Rating', 'rating'),
    'content_kind': ('XMP-jkmedia:ContentKind', 'kind'),
    'people_scope': ('XMP-jkmedia:PeopleScope', 'scope'),
    'ai_note': ('XMP-jkmedia:AINote', 'text'),
    'fictional_characters': ('XMP-jkmedia:FictionalCharacters', 'list'),
    'source_credits': ('XMP-jkmedia:SourceCredits', 'text'),
    'depicted_real_people': ('XMP-iptcExt:PersonInImage', 'list'),
    'photographer': ('XMP-jkmedia:Photographer', 'text'),
}
# Cleanup-only fields. Never create or assert a person's release with this skill.
REMOVE_ONLY = {
    'model_release_id': 'XMP-plus:ModelReleaseID',
    'model_release_status': 'XMP-plus:ModelReleaseStatus',
    'person_details': 'XMP-iptcExt:PersonInImageWDetails',
}
REAL_FIELDS = {'depicted_real_people', 'photographer'}


class Refused(Exception):
    pass


def dump(value, file=None):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if file:
        with pathlib.Path(file).open('x', encoding='utf-8') as handle:
            handle.write(text + '\n')
    else:
        print(text)


def sha(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run(argv, timeout=120):
    result = subprocess.run([str(v) for v in argv], shell=False, capture_output=True, timeout=timeout)
    if result.returncode:
        raise Refused('工具失败：' + str(argv[0]) + '\n' + result.stderr.decode('utf-8', 'replace')[:1500])
    return result.stdout


def executable(name, args, required=True):
    override = getattr(args, name.replace('-', '_'), None)
    found = str(pathlib.Path(override).expanduser().resolve()) if override else shutil.which(name)
    if not found or not pathlib.Path(found).is_file():
        if required:
            raise Refused('缺少工具：' + name + '；运行 doctor 查看安装来源。')
        return None
    return found


def exif_cmd(args):
    # Supplying our fixed config prevents loading ~/.ExifTool_config or cwd configs.
    return [executable('exiftool', args), '-config', str(BASE / 'exiftool-jk.config')]


def read_exif(path, args):
    if not executable('exiftool', args, False):
        return {}
    data = json.loads(run(exif_cmd(args) + ['-j', '-G1', '-s', '-struct', '--', str(path)]))
    return data[0]


def media_type(path):
    if path.suffix.lower() in IMAGE_EXT:
        return 'image'
    if path.suffix.lower() in VIDEO_EXT:
        return 'video'
    return 'other'


def expand_inputs(values):
    """Resolve the complete bounded batch before inspecting or writing media."""
    files = []
    seen = set()
    for value in values:
        path = pathlib.Path(value).expanduser().resolve(strict=True)
        candidates = path.iterdir() if path.is_dir() else [path]
        for candidate in candidates:
            if not candidate.is_file() or media_type(candidate) == 'other':
                if not path.is_dir():
                    raise Refused('输入必须为支持的图片或视频文件。')
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                raise Refused('inputs 包含重复文件：' + str(resolved))
            seen.add(resolved)
            files.append(resolved)
            if len(files) > MAX_FILES:
                raise Refused('单批最多512个媒体文件；本批未开始处理，请拆分输入。')
    if not files:
        raise Refused('输入中没有支持的图片或视频文件。')
    return sorted(files, key=str)


def video_info(path, args):
    return json.loads(run([executable('ffprobe', args), '-v', 'error', '-show_streams',
                           '-show_format', '-show_chapters', '-show_data_hash', 'sha256',
                           '-of', 'json', '-i', str(path)]))


def image_content(path):
    try:
        from PIL import Image
        from PIL.ImageSequence import Iterator
    except ImportError as exc:
        raise Refused('图片内容校验需要 Pillow；缺失时只能使用 sidecar 模式。') from exc
    frames = []
    try:
        with Image.open(path) as image:
            for frame in Iterator(image):
                frames.append({'size': frame.size, 'mode': frame.mode,
                               'pixels': hashlib.sha256(frame.tobytes()).hexdigest(),
                               'palette': frame.getpalette(),
                               'duration': frame.info.get('duration'),
                               'transparency': str(frame.info.get('transparency')),
                               'disposal': getattr(frame, 'disposal_method', None),
                               'icc': hashlib.sha256(frame.info.get('icc_profile', b'')).hexdigest(),
                               'dpi': frame.info.get('dpi'),
                               'orientation': frame.getexif().get(274)})
            return {'format': image.format, 'frames': frames, 'loop': image.info.get('loop')}
    except Exception as exc:
        raise Refused('无法完成图片内容校验：' + str(exc)) from exc


def video_content(path, args):
    info = video_info(path, args)
    streams = info.get('streams', [])
    for stream in streams:
        # Descriptive edits are container-level; all track tags remain protected.
        stream.pop('filename', None)
    fmt = info.get('format', {})
    protected = {k: fmt.get(k) for k in ('format_name', 'nb_streams', 'nb_programs', 'start_time', 'duration')}
    # Hash packet payloads AND per-packet timing, flags and order. Disk-backed to avoid
    # retaining an entire long video packet listing in RAM. Never decode/re-encode.
    cmd = [executable('ffprobe', args), '-v', 'error', '-show_packets', '-show_data_hash', 'sha256',
           '-show_entries', 'packet=stream_index,pts,dts,duration,flags,data_hash', '-of', 'compact', '-i', str(path)]
    with tempfile.TemporaryFile() as packets:
        proc = subprocess.run(cmd, shell=False, stdout=packets, stderr=subprocess.PIPE, timeout=900)
        if proc.returncode:
            raise Refused('音视频数据校验失败。')
        packets.seek(0)
        digest = hashlib.sha256()
        for block in iter(lambda: packets.read(1024 * 1024), b''):
            digest.update(block)
    # Source attachments are protected as well. Codec extradata hashes are included
    # in the stream records returned by ffprobe.
    return {'streams': streams, 'format': protected, 'chapters': info.get('chapters', []),
            'packets_sha256': digest.hexdigest()}


def content_signature(path, args):
    kind = media_type(path)
    if kind == 'image':
        return image_content(path)
    if kind == 'video':
        return video_content(path, args)
    raise Refused('不支持此格式的媒体内容校验；请选择 sidecar。')


def mkv_metadata(path, args):
    raw = run([executable('mkvextract', args), str(path), 'tags'])
    raw = re.sub(rb'<!--.*?-->', b'', raw, flags=re.S)
    raw = raw.replace(b'<!DOCTYPE Tags SYSTEM "matroskatags.dtd">', b'')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise Refused('拒绝包含外部实体或DOCTYPE的标签XML。')
    root = ET.fromstring(raw) if raw.strip() else ET.Element('Tags')
    metadata = {}
    for tag in root.findall('Tag'):
        for simple in tag.findall('Simple'):
            if simple.findtext('Name') == 'JK_METAINFO':
                value = json.loads(simple.findtext('String') or '{}')
                if not isinstance(value, dict) or metadata:
                    raise Refused('MKV自定义记录重复或无效。')
                metadata = value
    return root, metadata


def inspect(path, args):
    path = pathlib.Path(path).expanduser().resolve(strict=True)
    if not path.is_file():
        raise Refused('输入必须为本地普通文件。')
    first_hash = sha(path)
    raw = read_exif(path, args)
    normal = {}
    for field, (tag, _) in FIELDS.items():
        if tag in raw:
            normal[field] = raw[tag]
    if path.suffix.lower() == '.mkv' and executable('mkvextract', args, False):
        _, stored = mkv_metadata(path, args)
        normal.update(stored)
    signals = []
    for key, value in raw.items():
        name = key.lower()
        text = str(value).lower()
        if ('digitalsourcetype' in name and any(s in text for s in ('trainedalgorithmic', 'compositewithtrained'))
                or name.endswith(':aigenerated') and text in ('true', 'yes', '1')):
            signals.append({'tag': key, 'value': value, 'strength': 'metadata_declaration'})
        elif 'prompt' in name or name.endswith(':ainote'):
            if value:
                signals.append({'tag': key, 'value': value, 'strength': 'review_hint'})
    if normal.get('content_kind') in ('ai_generated', 'mixed', 'illustration'):
        signals.append({'tag': 'content_kind', 'value': normal['content_kind'], 'strength': 'metadata_declaration'})
    signed = any(('jumbf' in k.lower() or 'c2pa' in k.lower()) for k in raw) if raw else None
    if sha(path) != first_hash:
        raise Refused('读取期间文件发生变化，请重试只读预检。')
    return {'path': str(path), 'input_sha256': first_hash, 'bytes': path.stat().st_size,
            'media_type': media_type(path), 'metadata_tool_available': bool(raw),
            'metadata': normal, 'raw_metadata': raw, 'ai_signals': signals,
            'signed_or_c2pa_detected': signed,
            'review_template': {'kind': 'unknown', 'people_scope': 'unknown', 'basis': 'user',
                                'evidence': '', 'input_sha256': first_hash}}


def check_value(field, value):
    if field not in FIELDS:
        raise Refused('不允许的字段：' + field)
    typ = FIELDS[field][1]
    if typ in ('list', 'urls'):
        if not isinstance(value, list) or not value or any(not isinstance(v, str) or not v.strip() for v in value):
            raise Refused(field + ' 必须是非空字符串数组；删除请使用 remove。')
        if len(value) > 100:
            raise Refused('数组最多100项。')
        for entry in value:
            check_value('source_url' if typ == 'urls' else 'description', entry)
    elif typ == 'rating':
        if type(value) is not int or value not in range(-1, 6):
            raise Refused('rating 必须是 -1 到5的整数。')
    else:
        if not isinstance(value, str) or not value.strip() or '\x00' in value or len(value) > 32768:
            raise Refused(field + ' 必须是非空字符串，最多32768字符，不能含NUL。')
        if typ == 'url':
            from urllib.parse import urlsplit
            parsed = urlsplit(value)
            if parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.username or parsed.password:
                raise Refused(field + ' 必须是不含凭据的HTTP(S)网址。')
        if typ == 'kind' and value not in KINDS or typ == 'scope' and value not in SCOPES:
            raise Refused('无效内容分类：' + value)


def load_config(filename):
    path = pathlib.Path(filename).expanduser().resolve(strict=True)
    cfg = json.loads(path.read_text(encoding='utf-8'))
    allowed = {'version', 'inputs', 'output_dir', 'storage', 'set', 'remove', 'review', 'per_file'}
    if not isinstance(cfg, dict) or set(cfg) - allowed or type(cfg.get('version')) is not int or cfg['version'] != 1:
        raise Refused('配置格式无效或包含未知顶层键。')
    if cfg.get('storage', 'embedded') not in ('embedded', 'sidecar'):
        raise Refused('storage 只能为 embedded 或 sidecar。')
    if not isinstance(cfg.get('inputs'), list) or not cfg['inputs']:
        raise Refused('inputs 必须是文件或目录路径列表，不展开通配符。')
    def relative(value):
        p = pathlib.Path(value).expanduser()
        return (path.parent / p).resolve() if not p.is_absolute() else p.resolve()
    inputs = expand_inputs(relative(v) for v in cfg['inputs'])
    if len(set(inputs)) != len(inputs):
        raise Refused('inputs 包含重复文件。')
    output = relative(cfg.get('output_dir', './output'))
    overrides = {}
    for entry in cfg.get('per_file', []):
        if not isinstance(entry, dict) or set(entry) - {'path', 'set', 'remove', 'review'}:
            raise Refused('无效 per_file 配置。')
        key = relative(entry['path'])
        if key not in inputs or key in overrides:
            raise Refused('per_file 必须唯一且出现在inputs中。')
        overrides[key] = entry
    jobs = []
    outputs = set()
    for src in inputs:
        entry = overrides.get(src, {})
        changes = dict(cfg.get('set', {}))
        changes.update(entry.get('set', {}))
        remove = list(dict.fromkeys(cfg.get('remove', []) + entry.get('remove', [])))
        if set(changes) & set(remove):
            raise Refused('同一字段不能同时set和remove。')
        for field, value in changes.items():
            check_value(field, value)
        if any(v not in FIELDS and v not in REMOVE_ONLY for v in remove):
            raise Refused('remove中存在受保护或未知字段。')
        if not changes and not remove:
            raise Refused('没有需要修改的字段。')
        review = entry.get('review', cfg.get('review', {}))
        if not isinstance(review, dict):
            raise Refused('review必须为对象。')
        dest = output / (src.name + '.metadata.json' if cfg.get('storage') == 'sidecar' else src.name)
        if dest == src or dest in outputs:
            raise Refused('输出路径与原件相同，或多个输入的输出同名。')
        outputs.add(dest)
        jobs.append({'source': src, 'dest': dest, 'set': changes, 'remove': remove,
                     'review': review, 'storage': cfg.get('storage', 'embedded')})
    return jobs


def plan_job(job, args):
    data = inspect(job['source'], args)
    review = job['review']
    issues = []
    if set(review) - {'kind', 'people_scope', 'basis', 'evidence', 'input_sha256'}:
        issues.append('review包含未知字段。')
    kind = review.get('kind', 'unknown')
    scope = review.get('people_scope', 'unknown')
    if kind not in KINDS or scope not in SCOPES:
        issues.append('review分类无效。')
    if kind == 'unknown' or scope == 'unknown' or not isinstance(review.get('evidence'), str) or not review.get('evidence', '').strip():
        issues.append('需要完成内容预检：分类、人物范围及证据说明。')
    if review.get('basis') not in ('user', 'visual', 'provenance'):
        issues.append('basis必须为user、visual或provenance。')
    if review.get('input_sha256') != data['input_sha256']:
        issues.append('预检缺少当前文件SHA256，或文件已变化；请重新预检。')
    if (kind in ('ai_generated', 'illustration') and scope == 'real') or (kind == 'mixed' and scope == 'real'):
        issues.append('AI、动漫和混合画面不能声明为纯真人实拍；用fictional/mixed/none。')
    if kind == 'non_person' and scope != 'none':
        issues.append('non_person必须配people_scope=none。')
    real_ok = kind == 'photo' and scope == 'real'
    if (not real_ok and 'depicted_real_people' in job['set'] or
            not (kind == 'photo' and scope in ('real', 'none')) and 'photographer' in job['set']):
        issues.append('AI/动漫/混合/非人物素材不能添加真人身份或本画面摄影师字段；来源作者用source_credits。')
    if kind == 'photo' and any(s['strength'] == 'metadata_declaration' for s in data['ai_signals']):
        issues.append('已有AI/插画来源声明与photo分类冲突，需先核对来源。')
    for field, expected in (('content_kind', kind), ('people_scope', scope)):
        if field in job['set'] and job['set'][field] != expected:
            issues.append(field + '与预检分类不一致。')
        existing = data['metadata'].get(field)
        if existing and existing != expected and field not in job['set'] and field not in job['remove']:
            issues.append('已有' + field + '与本次预检冲突，需明确修正。')
    if not real_ok:
        for field in REAL_FIELDS:
            if field == 'photographer' and kind == 'photo' and scope == 'none':
                continue
            if data['metadata'].get(field) and field not in job['remove']:
                issues.append('已有真人相关字段' + field + '需显式remove，不能静默保留。')
        for field, tag in REMOVE_ONLY.items():
            if data['raw_metadata'].get(tag) and field not in job['remove']:
                issues.append('已有真人细节或授权字段' + field + '需显式清理。')
    if data['signed_or_c2pa_detected'] and job['storage'] == 'embedded':
        issues.append('检测到来源凭证/签名，仅支持sidecar，避免破坏凭证。')
    suffix = job['source'].suffix.lower()
    backend = 'sidecar'
    if job['storage'] == 'embedded':
        if suffix in EMBED_IMAGE or suffix in ('.mp4', '.mov', '.m4v'):
            backend = 'exiftool'
            if not executable('exiftool', args, False):
                issues.append('缺少ExifTool写入与完整预检依赖。')
        elif suffix == '.mkv':
            backend = 'mkvpropedit'
            for tool in ('mkvextract', 'mkvpropedit', 'exiftool'):
                if not executable(tool, args, False):
                    issues.append('缺少' + tool)
        else:
            issues.append('此格式尚未开放嵌入；请显式选择sidecar。')
        if data['media_type'] == 'image':
            try:
                image_content(job['source'])
            except Refused as exc:
                issues.append(str(exc))
        if data['media_type'] == 'video' and not executable('ffprobe', args, False):
            issues.append('视频写入需要ffprobe核验。')
    if job['dest'].exists():
        issues.append('输出文件已存在；换目录，程序不覆盖。')
    before = data['metadata']
    return {'source': str(job['source']), 'output': str(job['dest']), 'storage': job['storage'],
            'backend': backend, 'input_sha256': data['input_sha256'], 'review': review,
            'metadata_precheck_complete': data['metadata_tool_available'],
            'signed_or_c2pa_detected': data['signed_or_c2pa_detected'],
            'ai_signals': data['ai_signals'], 'issues': issues, 'ready': not issues,
            'changes': {key: {'before': before.get(key), 'after': value} for key, value in job['set'].items()},
            'remove': job['remove'], 'raw_before': data['raw_metadata']}


def tag_value_equal(field, expected, actual):
    if FIELDS[field][1] in ('list', 'urls'):
        actual = actual if isinstance(actual, list) else [actual]
        return sorted(actual) == sorted(expected)
    return str(expected) == str(actual)


def protect_metadata(before, after, changes, removed):
    allowed = {FIELDS[k][0].lower() for k in changes}
    allowed.update((FIELDS[k][0] if k in FIELDS else REMOVE_ONLY[k]).lower() for k in removed)
    def keep(key):
        lower = key.lower()
        return (':' in key and not lower.startswith(('system:', 'exiftool:', 'composite:'))
                and lower not in allowed and lower not in ('file:filesize', 'xmp-x:xmptoolkit'))
    b = {k: v for k, v in before.items() if keep(k)}
    a = {k: v for k, v in after.items() if keep(k)}
    return [k for k in sorted(set(b) | set(a)) if b.get(k) != a.get(k)]


def write_exif(path, job, args):
    cmd = exif_cmd(args) + ['-overwrite_original']
    for field in job['remove']:
        cmd.append('-' + (FIELDS[field][0] if field in FIELDS else REMOVE_ONLY[field]) + '=')
    for field, value in job['set'].items():
        tag, typ = FIELDS[field]
        if typ in ('list', 'urls'):
            cmd.append('-' + tag + '=')
            cmd.extend('-' + tag + '+=' + entry for entry in value)
        else:
            cmd.append('-' + tag + '=' + str(value))
    run(cmd + ['--', str(path)])


def write_mkv(path, job, args):
    root, existing = mkv_metadata(path, args)
    if any(k in REMOVE_ONLY for k in job['remove']):
        raise Refused('MKV不支持清理该标准字段。')
    for key in job['remove']:
        existing.pop(key, None)
    existing.update(job['set'])
    for tag in root.findall('Tag'):
        for simple in list(tag.findall('Simple')):
            if simple.findtext('Name') == 'JK_METAINFO':
                tag.remove(simple)
    tag = ET.SubElement(root, 'Tag')
    ET.SubElement(tag, 'Targets')
    simple = ET.SubElement(tag, 'Simple')
    ET.SubElement(simple, 'Name').text = 'JK_METAINFO'
    ET.SubElement(simple, 'String').text = json.dumps(existing, ensure_ascii=False)
    # Explicitly named generated data file; no user-supplied executable config.
    xmlfile = path.with_name(path.name + '.tags.xml')
    with xmlfile.open('xb') as handle:
        ET.ElementTree(root).write(handle, encoding='utf-8', xml_declaration=True)
    run([executable('mkvpropedit', args), str(path), '--tags', 'all:' + str(xmlfile)])


def apply_job(job, plan, args):
    src, dest = job['source'], job['dest']
    if sha(src) != plan['input_sha256']:
        raise Refused('源文件在预检后改变，停止。')
    dest.parent.mkdir(parents=True, exist_ok=True)
    if job['storage'] == 'sidecar':
        dump({'schema': 'jk-media-metainfo/1', 'embedded': False, 'source': str(src),
              'input_sha256': plan['input_sha256'], 'review': job['review'],
              'set': job['set'], 'remove': job['remove']}, dest)
        return {'source': str(src), 'output': str(dest), 'status': 'sidecar_saved',
                'embedded': False, 'source_unchanged': sha(src) == plan['input_sha256']}
    before_content = content_signature(src, args)
    with src.open('rb') as original, dest.open('xb') as copy:
        shutil.copyfileobj(original, copy)
    if plan['backend'] == 'exiftool':
        write_exif(dest, job, args)
    else:
        write_mkv(dest, job, args)
    after = inspect(dest, args)
    for field, value in job['set'].items():
        if not tag_value_equal(field, value, after['metadata'].get(field)):
            raise Refused('字段读回不一致：' + field + '；输出副本未通过核验。')
    for field in job['remove']:
        tag = FIELDS[field][0] if field in FIELDS else REMOVE_ONLY[field]
        if field in after['metadata'] or tag in after['raw_metadata']:
            raise Refused('字段删除未通过读回核验：' + field)
    unexpected = protect_metadata(plan['raw_before'], after['raw_metadata'], job['set'], job['remove'])
    if plan['backend'] == 'mkvpropedit':
        # MKV stores our fields in a single global JK_METAINFO tag. Other global
        # tag preservation is checked by comparing the original XML below.
        before_xml, _ = mkv_metadata(src, args)
        after_xml, _ = mkv_metadata(dest, args)
        def without_ours(root):
            result = []
            for tag in root.findall('Tag'):
                simples = [ET.tostring(s, encoding='unicode') for s in tag.findall('Simple') if s.findtext('Name') != 'JK_METAINFO']
                if simples:
                    result.append((ET.tostring(tag.find('Targets'), encoding='unicode') if tag.find('Targets') is not None else '', simples))
            return result
        if without_ours(before_xml) != without_ours(after_xml):
            raise Refused('MKV其他标签发生意外变化。')
        unexpected = [v for v in unexpected if v.startswith(('IFD', 'ExifIFD:', 'GPS:', 'XMP-'))]
    if unexpected:
        raise Refused('非目标元数据发生变化：' + ', '.join(unexpected[:20]))
    if before_content != content_signature(dest, args):
        raise Refused('媒体内容或受保护属性发生变化；输出副本未通过核验。')
    if sha(src) != plan['input_sha256']:
        raise Refused('原文件发生意外变化。')
    return {'source': str(src), 'output': str(dest), 'status': 'embedded_verified',
            'embedded': True, 'readback_verified': True, 'content_unchanged': True,
            'source_unchanged': True, 'input_sha256': plan['input_sha256'],
            'output_sha256': sha(dest), 'changed_fields': list(job['set']), 'removed_fields': job['remove']}


def doctor(args):
    names = ['exiftool', 'ffprobe', 'ffmpeg', 'mkvextract', 'mkvpropedit']
    paths = {name: executable(name, args, False) for name in names}
    versions = {}
    for name, path in paths.items():
        if path:
            try:
                flag = '-ver' if name == 'exiftool' else '-version' if name in ('ffmpeg', 'ffprobe') else '--version'
                cmd = exif_cmd(args) if name == 'exiftool' else [path]
                versions[name] = run(cmd + [flag], timeout=15).decode('utf-8', 'replace').splitlines()[0]
            except (Refused, subprocess.TimeoutExpired, OSError):
                versions[name] = 'version_unavailable'
    versions['python'] = platform.python_version()
    try:
        import PIL
        versions['Pillow'] = PIL.__version__
    except ImportError:
        versions['Pillow'] = 'missing'
    checks = {}
    for name, minimum in MIN_VERSIONS.items():
        raw = versions.get(name, 'missing')
        match = re.search(r'(\d+)\.(\d+)', raw)
        checks[name] = {'minimum': '.'.join(map(str, minimum)), 'detected': raw,
                        'ok': bool(match and tuple(map(int, match.groups())) >= minimum)}
    base_ok = checks['python']['ok'] and checks['exiftool']['ok']
    capabilities = {'metadata_precheck': base_ok,
                    'image_embedded': base_ok and checks['Pillow']['ok'],
                    'video_embedded': base_ok and checks['ffprobe']['ok'],
                    'mkv_embedded': base_ok and all(checks[n]['ok'] for n in ('ffprobe', 'mkvextract', 'mkvpropedit')),
                    'sidecar': checks['python']['ok']}
    return {'checks': checks, 'capabilities': capabilities,
            'status': 'ready' if all(capabilities.values()) else 'partial',
            'skill_version': VERSION, 'os': platform.system(), 'architecture': platform.machine(),
            'python': platform.python_version(),
            'tools': paths, 'tool_versions': versions,
            'installation': {'Darwin': 'Homebrew: exiftool、ffmpeg；MKV按需安装mkvtoolnix。',
                             'Windows': 'ExifTool、MKVToolNix官方发行包；FFmpeg从官网列出的构建来源获取。',
                             'Linux': '发行版签名仓库中的ExifTool、ffmpeg、mkvtoolnix。'},
            'note': '不自动安装、不调用网络、不修改系统配置。'}


def interactive(args):
    src = pathlib.Path(args.file).expanduser().resolve(strict=True)
    data = inspect(src, args)
    dump({'current': data['metadata'], 'ai_signals': data['ai_signals'], 'review_template': data['review_template']})
    review = data['review_template']
    review['kind'] = input('内容类别 photo/ai_generated/illustration/mixed/non_person/unknown：').strip()
    review['people_scope'] = input('人物范围 real/fictional/mixed/none/unknown：').strip()
    review['evidence'] = input('预检依据（画面、来源或用户说明）：').strip()
    print('可用字段：' + ', '.join(FIELDS))
    changes = json.loads(input('输入set JSON对象，例如 {"title":"示例","creator":["作者"]}：'))
    remove = json.loads(input('输入remove JSON数组；不删除填 []：'))
    cfg = {'version': 1, 'inputs': [str(src)], 'output_dir': str(pathlib.Path(args.output_dir).resolve()),
           'storage': args.storage, 'review': review, 'set': changes, 'remove': remove}
    dump(cfg, args.save_config)
    print('配置已保存；先用 plan 查看，再用 apply 执行已确认的修改。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for tool in ('exiftool', 'ffprobe', 'ffmpeg', 'mkvextract', 'mkvpropedit'):
        parser.add_argument('--' + tool, help='显式指定可信工具路径')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    for command in ('inspect', 'precheck'):
        child = sub.add_parser(command)
        child.add_argument('file', nargs='+', help='文件或目录；目录仅扫描当前层，最多512个媒体文件')
        child.add_argument('--report')
    for command in ('plan', 'apply'):
        child = sub.add_parser(command)
        child.add_argument('config')
        child.add_argument('--report')
    child = sub.add_parser('interactive')
    child.add_argument('file')
    child.add_argument('--save-config', required=True)
    child.add_argument('--output-dir', required=True)
    child.add_argument('--storage', choices=['embedded', 'sidecar'], default='embedded')
    args = parser.parse_args()
    try:
        if args.command == 'doctor':
            dump(doctor(args))
        elif args.command in ('inspect', 'precheck'):
            files = expand_inputs(args.file)
            results = []
            for file in files:
                result = inspect(file, args)
                result['visual_review_required'] = True
                result['precheck_status'] = 'needs_visual_or_user_review' if result['metadata_tool_available'] else 'partial_missing_exiftool'
                result['restriction'] = '未完成预检前不可添加真人身份、摄影或模特授权声明。'
                result['note'] = 'AI标识缺失不等于实拍；本程序不提供AI生成鉴定。'
                results.append(result)
            result = results[0] if len(results) == 1 else {'count': len(results), 'files': results}
            if args.report:
                dump(result, args.report)
            dump(result)
        elif args.command == 'interactive':
            interactive(args)
        else:
            jobs = load_config(args.config)
            runtime = doctor(args)
            plans = [plan_job(job, args) for job in jobs]
            for job, plan in zip(jobs, plans):
                needed = ['python']
                if job['storage'] == 'embedded':
                    needed += ['exiftool', 'Pillow'] if media_type(job['source']) == 'image' else ['exiftool', 'ffprobe']
                    if job['source'].suffix.lower() == '.mkv':
                        needed += ['mkvextract', 'mkvpropedit']
                for name in needed:
                    if not runtime['checks'][name]['ok']:
                        plan['issues'].append(name + '缺失、版本未知或低于兼容基线；运行doctor。')
                plan['ready'] = not plan['issues']
            public = [{k: v for k, v in p.items() if k != 'raw_before'} for p in plans]
            report = {'version': VERSION, 'time': dt.datetime.now(dt.timezone.utc).isoformat(),
                      'command': args.command, 'ready': all(p['ready'] for p in plans), 'plans': public}
            if args.command == 'apply':
                report['runtime'] = runtime
            if args.command == 'apply' and report['ready']:
                report['results'] = []
                for job, plan in zip(jobs, plans):
                    try:
                        report['results'].append(apply_job(job, plan, args))
                    except Exception as exc:
                        report['results'].append({'source': str(job['source']), 'output': str(job['dest']),
                                                  'status': 'failed_unverified', 'error': str(exc)[:2000]})
                        report['ready'] = False
                        break
                report['completed'] = report['ready']
            if args.report:
                dump(report, args.report)
            dump(report)
            if not report['ready']:
                return 2
    except (Refused, OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as exc:
        dump({'status': 'refused', 'error': str(exc)[:2000], 'originals_intentionally_modified': False})
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
