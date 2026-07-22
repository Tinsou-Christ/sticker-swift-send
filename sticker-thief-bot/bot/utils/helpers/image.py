import logging
import math
import tempfile
from typing import Optional

import numpy as np
from PIL import Image
from PIL.Image import Image as ImageType  # https://stackoverflow.com/a/58236618/13350541

logger = logging.getLogger(__name__)


class Options:
    def __init__(self, image_format="webp", max_size=512, square=False, keep_aspect_rateo=False, crop_transparent_areas=False):
        if image_format not in ("webp", "png"):
            raise ValueError("only png/webp formats are supported")

        self.image_format = image_format
        self.max_size = max_size
        self.square = square
        self.keep_aspect_rateo = keep_aspect_rateo
        self.crop_transparent_areas = crop_transparent_areas

    @property
    def crop(self):
        return self.crop_transparent_areas

    @property
    def ignore_aspect_rateo(self):
        return not self.keep_aspect_rateo

    @property
    def format(self):
        return self.image_format

    def __str__(self):
        return f"image_format: {self.image_format}; max_size: {self.max_size}: square: {self.square}; " \
               f"keep_aspect_rateo: {self.keep_aspect_rateo}; crop_transparent_areas: {self.crop_transparent_areas}"


def is_square(im: Image) -> bool:
    size = im.size
    return size[0] == size[1]


def crop_transparency(im: Image) -> ImageType:
    # https://stackoverflow.com/a/37942933

    image_data = np.asarray(im)
    try:
        image_data_bw = image_data[:, :, 3]  # just extract the alpha value
    except IndexError as ie:
        # numpy can't extract the 3rd index, probably because there is no alpha channel
        # return the image itself
        logger.warning("error while extracting the alpha channel values: %s", str(ie))
        return im.copy()  # we need to return a new object and not the old one, because it iwll be closed later

    # debug_print_image(image_data_bw)

    # print(image_data_bw)
    # print(np.where(image_data_bw.max(axis=0) > 0))
    # print(im.getpixel((0, 0)))

    # the original code was filtering anything with alpha vlaue > 0, see stack overflow url
    # it makes sense to filter naything > 0, but in our case it doesn't work: we need to filter anything that
    # doesn't have any alpha gradient. For some reason, many stickers's tranparent pixel actually have
    # an alpha value slightly above 0
    non_empty_columns = np.where(image_data_bw.max(axis=0) == 255)[0]  # filter columns with non-255 alpha value
    non_empty_rows = np.where(image_data_bw.max(axis=1) == 255)[0]

    # print("non_empty_columns", non_empty_columns)
    # print("non_empty_rows", non_empty_rows)

    crop_box = (min(non_empty_rows), max(non_empty_rows), min(non_empty_columns), max(non_empty_columns))
    # print(crop_box)

    image_data_new = image_data[crop_box[0]:crop_box[1] + 1, crop_box[2]:crop_box[3] + 1, :]

    new_image = Image.fromarray(image_data_new)

    return new_image


def get_correct_size(sizes, max_size):
    largest_side_index = 0 if sizes[0] > sizes[1] else 1
    shortest_side_index = 1 if largest_side_index == 0 else 0

    new = [None, None]
    new[largest_side_index] = max_size

    rateo = max_size / sizes[largest_side_index]

    new[shortest_side_index] = int(math.floor(sizes[shortest_side_index] * round(rateo, 4)))

    # logger.debug('correct sizes: %dx%d', new[0], new[1])
    return tuple(new)


def resize_keep_rateo(pil_image: Image, size: int) -> ImageType:
    # larger side must be 100px, the other one can be shorter
    scaled_size = get_correct_size(pil_image.size, max_size=size)
    pil_image = pil_image.resize(scaled_size, Image.ANTIALIAS)
    logger.debug("scaled size: %s", pil_image.size)

    canvas_width, canvas_height = size, size
    png_width, png_height = pil_image.size

    canvas_background = (255, 255, 255, 0)
    canvas_size = (size, size)
    canvas = Image.new(pil_image.mode, canvas_size, canvas_background)

    x1 = int(math.floor((canvas_width - png_width) / 2))
    y1 = int(math.floor((canvas_height - png_height) / 2))
    x2 = x1 + png_width
    y2 = y1 + png_height
    paste_coordinates = (x1, y1, x2, y2)
    logger.debug("paste coordinates: %s", paste_coordinates)

    canvas.paste(pil_image, paste_coordinates)

    pil_image.close()

    return canvas


class File:
    def __init__(self, input_image_bo: tempfile.SpooledTemporaryFile, options: Optional[Options] = None):
        self.input_image_bo = input_image_bo
        self.options = options or Options()
        self.pil_image: Image = Image.open(self.input_image_bo)
        self.result_tempfile = tempfile.SpooledTemporaryFile()

    def sticker_needs_resize(self, options: Optional[Options] = None):
        options = options or self.options  # maybe options were overridden by self.process()
        size = self.pil_image.size

        # one of the sies is larger than `max_size`...
        needs_resize = size[0] > options.max_size or size[1] > options.max_size
        # ...or none of the sides is `max_size`
        return needs_resize or (size[0] != options.max_size and size[1] != options.max_size)

    def process(self, options: Optional[Options] = None):
        options = options or self.options  # allow to override options

        logger.debug("options -> %s", options)

        if options.image_format not in ("png", "webp"):
            raise ValueError("image format must be either `webp` or `png`")
        if options.keep_aspect_rateo and not options.square:
            raise ValueError("`keep_aspect_rateo` is set to True, but `square` is not")

        if options.crop_transparent_areas:
            self.pil_image = crop_transparency(self.pil_image)

        if is_square(self.pil_image) or (options.square and not options.keep_aspect_rateo):
            # two secnarios:
            # - if the image is a square, just resize to the desired `max_size`
            # - if the image is not a square BUT we want a square and we don't care about the aspect rateo,
            #   just resize to the desired `max_size`
            self.pil_image = self.pil_image.resize((options.max_size, options.max_size), Image.ANTIALIAS)
        elif options.square and options.keep_aspect_rateo:
            # if the image is not a square but we want a square AND we want to keep the size rateo
            self.pil_image = resize_keep_rateo(self.pil_image, options.max_size)
        else:
            # the image is not a square, and we don't need it to be a square,
            # just make sure the largest size is `max_size`
            if self.sticker_needs_resize(options):
                correct_size = get_correct_size(self.pil_image.size, max_size=options.max_size)
                self.pil_image = self.pil_image.resize(correct_size, Image.ANTIALIAS)

        self.pil_image.save(self.result_tempfile, options.image_format)

        self.result_tempfile.seek(0)

        return self.result_tempfile

    def clone_result_tempfile(self, image_format=None, then_close=False):
        image_format = image_format or self.options.image_format

        new_tempfile = tempfile.SpooledTemporaryFile()
        self.pil_image.save(new_tempfile, image_format)

        if then_close:
            self.close()

        new_tempfile.seek(0)

        return new_tempfile

    def close(self):
        logger.debug("closing ImageFile...")
        self.pil_image.close()
        self.result_tempfile.close()
