import base64
import io

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED = {"JPEG", "PNG", "WEBP", "GIF", "BMP"}
Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard


class ImageError(ValueError):
    pass


def looks_like_image(data: bytes) -> bool:
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.format in ALLOWED
    except Exception:
        return False


def process_image(data: bytes) -> tuple[bytes, str, int, int]:
    """Fully decode, validate, auto-rotate, downscale and re-encode (strips EXIF/GPS
    metadata and any appended payload). Returns (bytes, mime, width, height)."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ALLOWED:
                raise ImageError("Unsupported image format. Please upload JPG, PNG, WEBP, GIF or BMP.")
            im.load()
            im = ImageOps.exif_transpose(im)
            if im.width < 32 or im.height < 32:
                raise ImageError("The image is too small to analyse (minimum 32x32 pixels).")
            alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
            im.thumbnail((2048, 2048))
            out = io.BytesIO()
            if alpha:
                im.convert("RGBA").save(out, "PNG", optimize=True)
                mime = "image/png"
            else:
                im.convert("RGB").save(out, "JPEG", quality=90)
                mime = "image/jpeg"
            return out.getvalue(), mime, im.width, im.height
    except ImageError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, ValueError):
        raise ImageError("This image is corrupted or could not be read. Try re-saving it as JPG or PNG.")


def to_data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"
