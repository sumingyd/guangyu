"""Raw binary ELF stripper - removes .debug_*, .symtab, .strtab sections
and compacts the file to eliminate the dead space left behind.

Handles both 32-bit and 64-bit little-endian ELF files.

安全策略（重要）：
  - 先完整解析并校验所有 section/segment 边界，任一越界直接放弃该文件；
  - 所有 section 数据先从源文件读入内存，再写入全新的输出缓冲区，
    绝不在原缓冲区上原地搬移（避免写入覆盖尚未读取的 section）；
  - 输出先写 .tmp 再原子替换，进程中断不会留下截断的 .so；
  - 遇到无法安全处理的格式（扩展 section 计数、section 与待删除区重叠等）
    直接跳过并报错，不产出可能损坏的库。

用法：
  python strip_elf.py [目录或 .so 路径 ...]
  默认目录为仓库内的 android/app/src/main/jniLibs（相对脚本位置）。
"""

import os
import struct
import sys

SHT_NULL = 0
SHT_NOBITS = 8
PT_LOAD = 1
SHN_XINDEX = 0xFFFF

# Sections to remove (by name prefix or exact match)
REMOVE_PREFIXES = ('.debug_',)
REMOVE_EXACT = {'.symtab', '.strtab'}


class ElfFormatError(Exception):
    """ELF 结构不受支持或已损坏，跳过该文件。"""


class ELFNotElfError(Exception):
    """输入文件不是 ELF。"""


def should_remove(name):
    return any(name.startswith(p) for p in REMOVE_PREFIXES) or name in REMOVE_EXACT


def strip_elf(filepath):
    """就地精简 ELF 文件，返回 (before, after)。

    解析失败时抛出 ElfFormatError / struct.error / OSError，调用方负责跳过，
    文件内容保持不变。
    """
    before = os.path.getsize(filepath)
    with open(filepath, 'rb') as f:
        data = f.read()

    if data[:4] != b'\x7fELF':
        raise ELFNotElfError(f"不是 ELF 文件: {filepath}")
    is64 = data[4] == 2
    if data[5] != 1:  # not little-endian
        raise ElfFormatError("仅支持 little-endian ELF")

    return _process(bytearray(data), filepath, before, is64)


def _parse_header(data, is64):
    """Parse ELF header, return dict of fields."""
    if is64:
        return {
            'e_phoff': struct.unpack_from('<Q', data, 0x20)[0],
            'e_shoff': struct.unpack_from('<Q', data, 0x28)[0],
            'e_phentsize': struct.unpack_from('<H', data, 0x36)[0],
            'e_phnum': struct.unpack_from('<H', data, 0x38)[0],
            'e_shentsize': struct.unpack_from('<H', data, 0x3A)[0],
            'e_shnum': struct.unpack_from('<H', data, 0x3C)[0],
            'e_shstrndx': struct.unpack_from('<H', data, 0x3E)[0],
        }
    return {
        'e_phoff': struct.unpack_from('<I', data, 0x1C)[0],
        'e_phentsize': struct.unpack_from('<H', data, 0x2A)[0],
        'e_phnum': struct.unpack_from('<H', data, 0x2C)[0],
        'e_shoff': struct.unpack_from('<I', data, 0x20)[0],
        'e_shentsize': struct.unpack_from('<H', data, 0x2E)[0],
        'e_shnum': struct.unpack_from('<H', data, 0x30)[0],
        'e_shstrndx': struct.unpack_from('<H', data, 0x32)[0],
    }


def _parse_sections(data, hdr, is64):
    """Parse all section headers, with bounds validation."""
    sections = []
    for i in range(hdr['e_shnum']):
        off = hdr['e_shoff'] + i * hdr['e_shentsize']
        if off + hdr['e_shentsize'] > len(data):
            raise ElfFormatError(f"section header {i} 越界")
        if is64:
            s = {
                'idx': i,
                'name_idx': struct.unpack_from('<I', data, off)[0],
                'type': struct.unpack_from('<I', data, off + 4)[0],
                'flags': struct.unpack_from('<Q', data, off + 8)[0],
                'addr': struct.unpack_from('<Q', data, off + 16)[0],
                'offset': struct.unpack_from('<Q', data, off + 24)[0],
                'size': struct.unpack_from('<Q', data, off + 32)[0],
                'link': struct.unpack_from('<I', data, off + 40)[0],
                'info': struct.unpack_from('<I', data, off + 44)[0],
                'addralign': struct.unpack_from('<Q', data, off + 48)[0],
                'entsize': struct.unpack_from('<Q', data, off + 56)[0],
            }
        else:
            s = {
                'idx': i,
                'name_idx': struct.unpack_from('<I', data, off)[0],
                'type': struct.unpack_from('<I', data, off + 4)[0],
                'flags': struct.unpack_from('<I', data, off + 8)[0],
                'addr': struct.unpack_from('<I', data, off + 12)[0],
                'offset': struct.unpack_from('<I', data, off + 16)[0],
                'size': struct.unpack_from('<I', data, off + 20)[0],
                'link': struct.unpack_from('<I', data, off + 24)[0],
                'info': struct.unpack_from('<I', data, off + 28)[0],
                'addralign': struct.unpack_from('<I', data, off + 32)[0],
                'entsize': struct.unpack_from('<I', data, off + 36)[0],
            }
        sections.append(s)
    return sections


def _parse_load_segments(data, hdr, is64):
    """Find end of all PT_LOAD segments."""
    load_end = 0
    for i in range(hdr['e_phnum']):
        off = hdr['e_phoff'] + i * hdr['e_phentsize']
        if off + hdr['e_phentsize'] > len(data):
            raise ElfFormatError(f"program header {i} 越界")
        p_type = struct.unpack_from('<I', data, off)[0]
        if p_type != PT_LOAD:
            continue
        if is64:
            p_offset = struct.unpack_from('<Q', data, off + 8)[0]
            p_filesz = struct.unpack_from('<Q', data, off + 32)[0]
        else:
            p_offset = struct.unpack_from('<I', data, off + 4)[0]
            p_filesz = struct.unpack_from('<I', data, off + 16)[0]
        load_end = max(load_end, p_offset + p_filesz)
    if load_end > len(data):
        raise ElfFormatError("PT_LOAD 段超出文件长度")
    return load_end


def _get_names(data, sections, shstrndx):
    """Resolve section names from the string table."""
    if shstrndx >= len(sections):
        raise ElfFormatError("e_shstrndx 越界")
    shstr = sections[shstrndx]
    end = shstr['offset'] + shstr['size']
    if end > len(data):
        raise ElfFormatError("section 名称表越界")
    strtab = bytes(data[shstr['offset']:end])
    for sec in sections:
        if sec['name_idx'] >= len(strtab):
            raise ElfFormatError(f"section {sec['idx']} 名称索引越界")
        name_end = strtab.find(b'\x00', sec['name_idx'])
        if name_end < 0:
            name_end = len(strtab)
        sec['name'] = strtab[sec['name_idx']:name_end].decode('ascii', 'replace')


def _process(data, filepath, before, is64):
    hdr = _parse_header(data, is64)
    if hdr['e_shoff'] == 0 or hdr['e_shnum'] == 0:
        raise ElfFormatError("无 section header table（已 strip 或格式不适用）")
    if hdr['e_shnum'] >= 0xFF00:
        raise ElfFormatError("扩展 section 计数（e_shnum >= 0xFF00）暂不支持")
    if hdr['e_shstrndx'] == SHN_XINDEX:
        raise ElfFormatError("扩展 section 名称索引（SHN_XINDEX）暂不支持")
    if hdr['e_shentsize'] == 0:
        raise ElfFormatError("e_shentsize 为 0")

    sections = _parse_sections(data, hdr, is64)
    _get_names(data, sections, hdr['e_shstrndx'])
    load_end = _parse_load_segments(data, hdr, is64)

    kept = [s for s in sections if not should_remove(s['name'])]
    removed = [s for s in sections if should_remove(s['name'])]
    if not removed:
        return before, before

    removed_with_data = [
        s for s in removed
        if s['type'] not in (SHT_NULL, SHT_NOBITS) and s['size'] > 0
    ]
    if not removed_with_data:
        return _rebuild(data, sections, kept, removed, hdr, is64, filepath, before)

    removed_start = min(s['offset'] for s in removed_with_data)
    kept_idx = {s['idx'] for s in kept}

    for s in sections:
        if s['type'] in (SHT_NULL, SHT_NOBITS) or s['size'] == 0:
            continue
        if s['offset'] + s['size'] > len(data):
            raise ElfFormatError(f"section {s['name']} 数据越界")
        # 与待删除区部分重叠的保留段无法安全搬移
        if s['idx'] in kept_idx and s['offset'] < removed_start < s['offset'] + s['size']:
            raise ElfFormatError(f"section {s['name']} 与待删除区重叠，跳过")

    kept_before_end = load_end
    for s in kept:
        if s['type'] not in (SHT_NULL, SHT_NOBITS) and s['size'] > 0:
            if s['offset'] + s['size'] <= removed_start:
                kept_before_end = max(kept_before_end, s['offset'] + s['size'])
    kept_before_end = max(kept_before_end, 0)

    kept_to_move = sorted(
        [s for s in kept
         if s['type'] not in (SHT_NULL, SHT_NOBITS)
         and s['size'] > 0
         and s['offset'] >= removed_start],
        key=lambda s: s['offset']
    )

    # 先把源数据全部读出，再写入全新缓冲区，彻底避免原地覆盖。
    moved_blobs = [(s, bytes(data[s['offset']:s['offset'] + s['size']])) for s in kept_to_move]
    out = bytearray(data[:kept_before_end])

    for s, blob in moved_blobs:
        align = s.get('addralign', 1) or 1
        if align > 1:
            pad = (-len(out)) % align
            if pad:
                out.extend(b'\x00' * pad)
        s['offset'] = len(out)
        out.extend(blob)

    return _rebuild(data, sections, kept, removed, hdr, is64, filepath, before, out=out)


def _rebuild(data, sections, kept, removed, hdr, is64, filepath, before, out=None):
    """Rebuild section header table without removed sections and
    write the compacted file atomically."""

    removed_set = {s['idx'] for s in removed}

    old_to_new = {}
    for new_idx, sec in enumerate(kept):
        old_to_new[sec['idx']] = new_idx

    new_shdr = bytearray()
    for sec in kept:
        off = hdr['e_shoff'] + sec['idx'] * hdr['e_shentsize']
        shdr = bytearray(data[off:off + hdr['e_shentsize']])
        if len(shdr) != hdr['e_shentsize']:
            raise ElfFormatError("section header 数据不完整")

        if is64:
            struct.pack_into('<Q', shdr, 24, sec['offset'])
        else:
            struct.pack_into('<I', shdr, 16, sec['offset'])

        link_off = 40 if is64 else 24
        sh_link = struct.unpack_from('<I', shdr, link_off)[0]
        if sh_link in old_to_new:
            struct.pack_into('<I', shdr, link_off, old_to_new[sh_link])
        elif sh_link in removed_set:
            struct.pack_into('<I', shdr, link_off, 0)

        info_off = 44 if is64 else 28
        sh_info = struct.unpack_from('<I', shdr, info_off)[0]
        if sh_info in old_to_new:
            struct.pack_into('<I', shdr, info_off, old_to_new[sh_info])
        elif sh_info in removed_set:
            struct.pack_into('<I', shdr, info_off, 0)

        new_shdr.extend(shdr)

    new_shstrndx = old_to_new.get(hdr['e_shstrndx'], 0)

    max_data_end = 0
    for sec in kept:
        if sec['type'] not in (SHT_NULL, SHT_NOBITS) and sec['size'] > 0:
            max_data_end = max(max_data_end, sec['offset'] + sec['size'])

    if out is None:
        out = bytearray(data[:max_data_end])
    else:
        # 缓冲区可能因 load_end/对齐而长于最后一个 section 的末尾，
        # 必须以实际长度为准，否则 header 偏移会指向错误位置。
        max_data_end = max(max_data_end, len(out))

    new_shoff = (max_data_end + 7) & ~7
    while len(out) < new_shoff:
        out.append(0)
    out.extend(new_shdr)

    if is64:
        struct.pack_into('<Q', out, 0x28, new_shoff)
        struct.pack_into('<H', out, 0x3C, len(kept))
        struct.pack_into('<H', out, 0x3E, new_shstrndx)
    else:
        struct.pack_into('<I', out, 0x20, new_shoff)
        struct.pack_into('<H', out, 0x30, len(kept))
        struct.pack_into('<H', out, 0x32, new_shstrndx)

    # 原子写入：先写同目录 .tmp，再替换，避免中断留下截断文件
    mode = os.stat(filepath).st_mode
    tmp_path = filepath + ".tmp"
    try:
        with open(tmp_path, 'wb') as f:
            f.write(out)
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, filepath)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return before, len(out)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dirs = sys.argv[1:] if len(sys.argv) > 1 else [
        os.path.join(script_dir, "android", "app", "src", "main", "jniLibs"),
    ]

    total_b = total_a = 0
    processed = 0
    failed = 0
    for base in base_dirs:
        if not os.path.exists(base):
            print(f"Not found: {base}")
            failed += 1
            continue
        if os.path.isfile(base):
            candidates = [base]
        else:
            candidates = [
                os.path.join(root, f)
                for root, _, files in os.walk(base)
                for f in sorted(files)
                if f.endswith('.so')
            ]
        for path in candidates:
            if not path.endswith('.so'):
                continue
            rel = os.path.relpath(path)
            try:
                b, a = strip_elf(path)
            except (ElfFormatError, ELFNotElfError, struct.error, OSError) as e:
                print(f"{rel:60s} 跳过: {e}")
                failed += 1
                continue
            processed += 1
            saved = b - a
            pct = saved / b * 100 if b else 0
            print(f"{rel:60s} {b / 1048576:6.1f} -> {a / 1048576:6.1f} MB  "
                  f"(saved {saved / 1048576:5.1f} MB, {pct:.0f}%)")
            total_b += b
            total_a += a

    if processed:
        print(f"\n{'TOTAL':60s} {total_b / 1048576:6.1f} -> "
              f"{total_a / 1048576:6.1f} MB  "
              f"(saved {(total_b - total_a) / 1048576:5.1f} MB, "
              f"{(total_b - total_a) / total_b * 100:.0f}%)")

    if failed:
        print(f"失败/跳过: {failed} 个文件", file=sys.stderr)
        return 1
    if processed == 0:
        print("未找到任何 .so 文件", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
