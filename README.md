
# Image Compression and Conversion Tool

This program compresses and converts images and icons to binary inside an [image_data.h](image_data.h) header file. You can use for example [stb_image](https://github.com/nothings/stb/blob/master/stb_image.h) to load the images into a texture SRV. The compression includes various methods to optimize the size and usability of the images, particularly for icons.

## Features

1. **Alpha Mapping Compression**
   - Maps all values to use only the alpha channel.
   - Decompresses with `255, 255, 255, a`.
   - Splits size by 4 but removes any color from the image.
   - Ideal for icons, allowing the use of a tint color to change the icon color.

2. **Image Resizing**
   - Resizes images to smaller dimensions.
   - Suitable for icons, which do not need to be large.

3. **Raw PNG Binary Saving**
   - Option to save images as raw PNG binary.
   - Can save space for smaller images.
   - Automatically detects if best to use

4. **Run-Length Encoding (RLE) Compression**
   - Uses RLE for compression.
   - Saves significant space.

## Usage

1. **Alpha Mapping Compression**
   - The alpha values are extracted and mapped, discarding color information.
   - During decompression, color can be restored using a predefined tint.

2. **Image Resizing**
   - Images are resized to the specified dimensions.

3. **Raw PNG Binary Saving**
   - Optionally saving the image data as raw PNG binary when smaller.

4. **RLE Compression**
   - Apply RLE compression to reduce file size further.

5. Make sure compression worked by checking that the images in the /decompressed directory look good

## Installation

1. Clone the repository.
2. Create an assets directory if not already existing and place any .png images there
3. Edit config at the top of `main.py` to fit your needs
4. Run!
5. Use generated header file directly in your projects

## Example Usage

An example of how to use the generated `image_data.h` file with `stb_image` to load an image into a texture:

```c
#include <stb_image.h>
#include "image_data.h"

// Example function to load image from image_data.h
bool loadImage(const std::string& imageName) {
   if (imageMap.find(imageName) != imageMap.end()) {
      ImageData imageData = imageMap[imageName];
        
      int width, height, channels;
      unsigned char* data = nullptr;

      width = imageData.width;
      height = imageData.height;
      
      if (imageData.isRawPng) {
         data = stbi_load_from_memory(imageData.data, imageData.size, &width, &height, &channels, 0);
      } else {
         unsigned char* decompressed_data = rle_decompress(imageData.data, imageData.size, imageData.originalSize);

         size_t max_size = imageData.alphaOnly ? imageData.originalSize * 4 : imageData.originalSize;
         data = (unsigned char*)malloc(max_size);

         if (imageData.alphaOnly) {
            // Decompress alpha-only image
            for (unsigned int i = 0; i < imageData.originalSize; ++i) {
               data[i * 4 + 0] = 255; // R
               data[i * 4 + 1] = 255; // G
               data[i * 4 + 2] = 255; // B
               data[i * 4 + 3] = decompressed_data[i]; // A
            }
         }
         else
            data = decompressed_data;
      }
        
      if (data) {
         // Use the image data, e.g., upload to a texture
         // Example: glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, data);
         
         stbi_image_free(data);

         return true;
      } else {
         std::cerr << "Unknown Error! Data is null\n";

         return false;
      }
   } else {
      std::cerr << "Image not found!\n";

      return false;
   }
}