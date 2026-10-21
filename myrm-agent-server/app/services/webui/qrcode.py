"""二维码生成服务

用于 WebUI 扫码访问功能：
- 生成终端显示的 ASCII 艺术二维码
- 生成浏览器显示的 PNG 图片二维码
"""

import io
import logging
from functools import lru_cache

import qrcode
from PIL import Image

logger = logging.getLogger(__name__)


@lru_cache(maxsize=32)
def generate_qrcode_ascii(data: str, border: int = 1) -> str:
    """生成 ASCII 艺术二维码（终端显示）

    使用 LRU 缓存避免重复生成相同的二维码。

    Args:
        data: 要编码的数据（URL）
        border: 边框大小

    Returns:
        ASCII 艺术字符串

    Raises:
        ValueError: 当数据为空时
    """
    if not data:
        raise ValueError("QR code data cannot be empty")

    logger.debug(f"Generating ASCII QR code for: {data}")

    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)

        # 使用 Unicode 方块字符绘制
        output = io.StringIO()
        matrix = qr.get_matrix()
        for row in matrix:
            line = ""
            for cell in row:
                # 使用全角空格和█字符
                line += "██" if cell else "  "
            output.write(line + "\n")

        result = output.getvalue()
        logger.debug(f"ASCII QR code generated successfully ({len(result)} chars)")
        return result
    except Exception as e:
        logger.error(f"Failed to generate ASCII QR code: {e}")
        raise


@lru_cache(maxsize=32)
def generate_qrcode_image(data: str, size: int = 400) -> bytes:
    """生成二维码图片（PNG 格式）

    使用 LRU 缓存避免重复生成相同的二维码。

    Args:
        data: 要编码的数据（URL）
        size: 图片大小（像素）

    Returns:
        PNG 图片的字节数据

    Raises:
        ValueError: 当数据为空或尺寸无效时
    """
    if not data:
        raise ValueError("QR code data cannot be empty")
    if size < 100 or size > 2000:
        raise ValueError("QR code size must be between 100 and 2000 pixels")

    logger.debug(f"Generating QR code image for: {data} (size: {size}px)")

    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        # 生成图片
        img = qr.make_image(fill_color="black", back_color="white")

        # 确保是 PIL Image 对象
        if not isinstance(img, Image.Image):
            img = img.convert("RGB")

        # 调整大小
        img = img.resize((size, size), Image.Resampling.LANCZOS)

        # 转换为字节
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        result = buffer.getvalue()

        logger.debug(f"QR code image generated successfully ({len(result)} bytes)")
        return result
    except Exception as e:
        logger.error(f"Failed to generate QR code image: {e}")
        raise


def generate_webui_url_with_token(host: str, port: int, temp_token: str | None = None) -> str:
    """生成带临时 Token 的 WebUI URL

    Args:
        host: 主机地址
        port: 端口
        temp_token: 临时访问 Token（可选）

    Returns:
        完整的访问 URL

    Examples:
        >>> generate_webui_url_with_token("192.168.1.100", 25808)
        'http://192.168.1.100:25808'
        >>> generate_webui_url_with_token("192.168.1.100", 25808, "abc123")
        'http://192.168.1.100:25808/?setup_token=abc123'
    """
    base_url = f"http://{host}:{port}"

    if temp_token:
        # 带 Token 的 URL，用于首次设置
        logger.debug(f"Generated WebUI URL with token for {host}:{port}")
        return f"{base_url}/?setup_token={temp_token}"

    logger.debug(f"Generated WebUI URL for {host}:{port}")
    return base_url
