ALPHA_ONLY = True # Stores only the alpha values of the images
RESIZE_IMAGES = True # Resizes the images
RESIZE_SIZE = (64, 64)

import os, re, time, cProfile, pstats
from PIL import Image, ImageOps
import io
from base64 import b64encode

import cv2
import numpy as np
from collections import Counter

def profile(func):
    def wrapper(*args, **kwargs):
        with cProfile.Profile() as profiler:
            result = func(*args, **kwargs)

        print("Function:", func.__name__)
        ps = pstats.Stats(profiler).sort_stats('tottime')
        ps.print_stats()

        return result

    return wrapper

def timer(func=None, *, count=1):
    if func is None:
        return lambda func: timer(func, count=count)
    
    def wrapper(*args, **kwargs):
        total_time = 0
        for i in range(count):
            start = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            total_time += elapsed
        
        average_time = total_time / count
        print(f"Total time for {count} executions: {round(total_time, 3)}s")
        print(f"Average time per execution: {round(average_time, 3)}s")
        
        return result
    
    return wrapper

def read_image(file_path: str) -> tuple[bytearray, int, int]:
    """
    Reads a image and returns a tuple of (bytes, width, height)
    """
    with open(file_path, 'rb') as f:
        img = Image.open(f)
        width, height = img.size
        image_data = bytearray(img.tobytes())
        return (image_data, width, height)

def generate_header(image_data_map: dict):
    """
    Generates a image_data.h file that contains all images
    """
    header = "#pragma once\n\n"
    header += "#include <map>\n"
    header += "#include <string>\n\n"
    header += "struct ImageData {\n"
    header += "    unsigned char* data;\n"
    header += "    unsigned int size;\n"
    header += "    unsigned int width;\n"
    header += "    unsigned int height;\n"
    header += "    unsigned int originalSize;\n"
    header += "    bool isRawPng;\n"
    header += "    bool alphaOnly;\n"
    header += "};\n\n"
    header += "std::map<std::string, ImageData> imageMap = {\n"

    for file_name, (image_data, width, height, original_size, is_raw_png, alpha_only) in image_data_map.items():
        image_data_str = ','.join(map(str, image_data))
        data_len = len(image_data)
        header += f'{{ "{file_name}", {{ new unsigned char[{data_len}] {{ {image_data_str} }}, {data_len}, {width}, {height}, {original_size}, {"true" if is_raw_png else "false"}, {"true" if alpha_only else "false"} }} }},\n'

    header += "};"

    return header

def extract_image_data(header: str):
    """
    Extracts image data from a header file
    """
    extracted_image_data_map = {}
    lines: list[str] = header.split('\n')
    i = 14
    while i < len(lines):
        line = lines[i]
        #line = "{ \"bug.png\", { new unsigned char[6439] { 0, 92, 0, 0, 3, 255, 1, 0, 4, 0, 0, 3, 255, 101}, 64, 64 } }"
        pattern = r'\"(.*?)\", \{ new unsigned char\[(\d+)\] \{(.*?)\}, (\d+), (\d+), (\d+), (\d+), (.*?) \}'
        match = re.search(pattern, line)
        if match:
            filename = match.group(1)
            length = match.group(2)
            image_data = bytearray(map(int, match.group(3).split(',')))
            width = int(match.group(4))
            height = int(match.group(5))
            original_size = int(match.group(6))
            is_raw_png = bool(match.group(7))
            alpha_only = bool(match.group(8))
            extracted_image_data_map[filename] = (image_data, int(length), width, height, original_size, is_raw_png, alpha_only)

        i += 1
    return extracted_image_data_map

def resize_images(assets_directory: str, output_size: tuple[int, int] = (128, 128)) -> str:
    """
    Resizes all image in a directory to a specific size, return the output directory
    """
    # Ensure the directory path ends with a slash
    if not assets_directory.endswith('/'):
        assets_directory += '/'

    # Create a directory for resized images if it doesn't exist
    output_directory = assets_directory + 'resized/'
    os.makedirs(output_directory, exist_ok=True)

    # Loop through all files in the directory
    for filename in os.listdir(assets_directory):
        if filename.endswith('.png'):
            # Open the image
            with Image.open(assets_directory + filename) as img:
                # Resize the image
                img_resized = img.resize(output_size, Image.LANCZOS)
                # Save the resized image
                img_resized.save(output_directory + filename)

    print("Resizing complete.")
    return output_directory

def fix_data_for_rle(data: bytearray) -> None:
    """
    Replaces all rle flags with a value close enough so that rle functions correctly and returns a copy
    """
    copy = data.copy()
    i = copy.find(2)
    while i != -1:
        copy[i] = 1
        i = copy.find(2, i + 1)

    return copy

def rle_compress(data: bytearray) -> bytearray:
    """
    Compresses a bytearray of data using rle (Run-length encoding)
    and returns the compressed data
    """
    compressed_data = bytearray()
    length = len(data)
    i = 0
    while i < length:
        count = 1
        max_count = min(255, length - i)  # Maximum count value
        while count < max_count and data[i] == data[i + count]:
            count += 1
        if count > 2:
            compressed_data.extend([2, count, data[i]]) # 2 indicates a run
        else:
            compressed_data.append(data[i])
            if count == 2:
                compressed_data.append(data[i + 1])
        i += count
    return compressed_data

def rle_decompress(compressed_data: bytearray) -> bytearray:
    """
    Decompresses a bytearray of rle compressed data and returns the decompressed data
    """
    decompressed_data = bytearray()
    i = 0
    while i < len(compressed_data):
        if compressed_data[i] == 2:  # Indicates a run
            run_length = compressed_data[i + 1]
            pixel_value = compressed_data[i + 2]
            decompressed_data.extend([pixel_value] * run_length)
            i += 3
        else:
            decompressed_data.append(compressed_data[i])
            i += 1
    return decompressed_data

def generate_bytearray_of_length(val, length):
    return bytearray([val] * length)

def bytearray_differences(bytearray1: bytearray, bytearray2: bytearray) -> str:
    """
    Checks the differences between to byte arrays
    and returns a string of all differences and indecies
    """
    text = ""
    # Ensure both bytearrays are of the same length
    if len(bytearray1) != len(bytearray2):
        text += "Bytearrays must be of the same length.\n"
    
    # Iterate through each byte in the bytearrays
    num_difs = 0
    for i in range(len(bytearray1)):
        # Check if the bytes are different
        if bytearray1[i] != bytearray2[i]:
            num_difs += 1
            # Print the difference along with the index
            text += f"Difference at index {i}: {hex(bytearray1[i])} != {hex(bytearray2[i])}\n"
    
    if num_difs == 0:
        text = "No differences found!"
    else:
        text = f"{num_difs} differences found:\n{text}"

    return text

def get_alpha_values(image_data: bytearray) -> bytearray:
    """
    Converts a bytearray of a RGBA image to a bytearray of alpha values
    """
    return image_data[3::4]

def alpha_vals_to_image_data(alpha_values: bytearray) -> bytearray:
    """
    Converts a bytearray of alpha values to a bytearray of a RGBA image
    """
    image_data = bytearray()
    for i in alpha_values:
        image_data.extend([255, 255, 255, i])

    return image_data

def main():
    start = time.time()
    image_data_map = {}

    bytes_saved = 0

    # Iterate through all .png files in the assets directory
    assets_dir = "assets"

    if not os.path.exists(assets_dir):
        print("No assets found!")
        return

    if RESIZE_IMAGES:
        assets_dir = resize_images(assets_dir, RESIZE_SIZE)

    original_size = 0
    for file_name in os.listdir(assets_dir):
        if file_name.endswith(".png"):
            file_path = os.path.join(assets_dir, file_name)
            image_data, width, height = read_image(file_path)
            orig_size = len(image_data)
            saved = 0

            alpha_only = False
            if ALPHA_ONLY:
                alpha_only = True
                image_data = get_alpha_values(image_data)

            adjusted_image_data = fix_data_for_rle(image_data)
            decompressed_size = len(adjusted_image_data)
            image_data = rle_compress(adjusted_image_data)

            is_raw_png = False
            with open(file_path, 'rb') as fp:
                raw_png_data = fp.read()

                if (len(raw_png_data) < len(image_data)):
                    image_data = raw_png_data
                    is_raw_png = True
                    alpha_only = False

            original_size += orig_size
            saved += orig_size - len(image_data)
            bytes_saved += saved
            print(f"Image: {file_name}\nSaved {saved:_} bytes!")

            image_data_map[file_name] = (image_data, width, height, decompressed_size, is_raw_png, alpha_only)

    # Generate the header file
    header = generate_header(image_data_map)

    with open("image_data.h", "w") as header_file:
        header_file.write(header)

    print(f"Header file generated in {round(time.time() - start, 3)}s")
    print(f"Compression saved {bytes_saved:_} bytes! ({round((bytes_saved / original_size) * 100, 3)}%)")

    decompressed_dir = os.path.join(assets_dir, "decompressed")
    os.makedirs(decompressed_dir, exist_ok=True)

    for file_name, file_data in image_data_map.items():
        file_path = os.path.join(decompressed_dir, file_name)
        image_data = file_data[0]
        is_raw_png = file_data[4]

        if not is_raw_png:
            image_data = rle_decompress(image_data)

            if ALPHA_ONLY:
                image_data = alpha_vals_to_image_data(image_data)

            width = file_data[1]
            height = file_data[2]

            expected_length = width * height * 4
            if len(image_data) != expected_length:
                raise ValueError(f"Expected {expected_length} bytes, but got {len(image_data)} bytes.")

            image = Image.frombytes('RGBA', (width, height), bytes(image_data))
            image.save(file_path)
        else:
            with open(file_path, 'wb') as fp:
                fp.write(image_data)

if __name__ == "__main__":
    main()