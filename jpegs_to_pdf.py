#!/usr/bin/env python3
"""Minimal pure-Python JPEG-to-PDF converter (no external dependencies)"""

import struct
import zlib


def jpegs_to_pdf(image_paths, output_path):
    """
    Create a PDF from a list of JPEG files.
    Each JPEG becomes one page.
    """
    images = []
    for path in image_paths:
        with open(path, 'rb') as f:
            data = f.read()
        # Verify it's a JPEG
        if data[:2] != b'\xff\xd8':
            raise ValueError(f"Not a JPEG: {path}")
        # Get dimensions from JPEG headers
        width, height = _get_jpeg_size(data)
        images.append((data, width, height))
    
    num_pages = len(images)
    objects = []
    
    # We'll build objects incrementally
    # Object 1: Catalog
    # Object 2: Pages
    # Objects 3,5,7,...: Page objects
    # Objects 4,6,8,...: Content streams
    # Objects 5+n*2,7+n*2,...: Image XObjects
    
    obj_catalog = 1
    obj_pages = 2
    page_objs = []
    content_objs = []
    image_objs = []
    
    for i, (jpeg_data, width, height) in enumerate(images):
        page_obj = 3 + i * 3
        content_obj = 4 + i * 3
        image_obj = 5 + i * 3
        page_objs.append(page_obj)
        content_objs.append(content_obj)
        image_objs.append(image_obj)
    
    # Build object definitions
    pdf_objects = []
    
    # Catalog
    pdf_objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    
    # Pages
    kids = b" ".join([f"{p} 0 R".encode() for p in page_objs])
    pdf_objects.append(f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {num_pages} >>\nendobj\n".encode())
    
    # Page objects, content streams, and image objects
    for i, (jpeg_data, width, height) in enumerate(images):
        page_obj = page_objs[i]
        content_obj = content_objs[i]
        image_obj = image_objs[i]
        
        # Content stream: draw image to fill the page
        # MediaBox is [0 0 width height]
        content_stream = f"q\n{width} 0 0 {height} 0 0 cm\n/Im0 Do\nQ".encode()
        compressed_content = zlib.compress(content_stream)
        
        # Page object
        page_dict = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Contents {content_obj} 0 R /Resources << /XObject << /Im0 {image_obj} 0 R >> >> >>".encode()
        pdf_objects.append(f"{page_obj} 0 obj\n<< {page_dict.split(b'<< ')[1].split(b' >>')[0]} >>\nendobj\n".encode())
        
        # Content stream object
        pdf_objects.append(f"{content_obj} 0 obj\n<< /Length {len(compressed_content)} /Filter /FlateDecode >>\nstream\n".encode())
        pdf_objects.append(compressed_content)
        pdf_objects.append(b"\nendstream\nendobj\n")
        
        # Image XObject
        jpeg_length = len(jpeg_data)
        image_dict = f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {jpeg_length} >>".encode()
        pdf_objects.append(f"{image_obj} 0 obj\n<< {image_dict.split(b'<< ')[1].split(b' >>')[0]} >>\nstream\n".encode())
        pdf_objects.append(jpeg_data)
        pdf_objects.append(b"\nendstream\nendobj\n")
    
    # Build cross-reference table
    # First, calculate offsets
    xref_offsets = []
    current_offset = 0
    
    # PDF header
    header = b"%PDF-1.4\n"
    current_offset += len(header)
    
    # We'll add all objects and track offsets
    obj_data = b""
    for obj in pdf_objects:
        xref_offsets.append(current_offset)
        obj_data += obj
        current_offset += len(obj)
    
    # xref
    xref_start = current_offset
    xref = f"xref\n0 {len(pdf_objects) + 1}\n".encode()
    xref += b"0000000000 65535 f \n"
    for offset in xref_offsets:
        xref += f"{offset:010d} 00000 n \n".encode()
    
    # trailer
    trailer = f"trailer\n<< /Size {len(pdf_objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode()
    
    with open(output_path, 'wb') as f:
        f.write(header)
        f.write(obj_data)
        f.write(xref)
        f.write(trailer)


def _get_jpeg_size(data):
    """Extract width and height from JPEG binary data"""
    # JPEG structure: SOI (FF D8), then markers
    # SOF0/SOF2 marker (FF C0/C2) contains width/height
    i = 2  # Skip SOI
    while i < len(data) - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xD8 or marker == 0xD9:  # SOI or EOI
            i += 2
            continue
        if marker == 0xDA:  # SOS - start of scan, no more markers after this
            break
        # Length of this segment
        seg_len = struct.unpack('>H', data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2):  # SOF
            height = struct.unpack('>H', data[i + 4:i + 6])[0]
            width = struct.unpack('>H', data[i + 6:i + 8])[0]
            return width, height
        i += 2 + seg_len
    return 0, 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: jpegs_to_pdf.py output.pdf input1.jpg [input2.jpg ...]")
        sys.exit(1)
    jpegs_to_pdf(sys.argv[2:], sys.argv[1])
    print(f"Created {sys.argv[1]}")
