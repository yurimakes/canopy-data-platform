"""Small, re-encoded profile thumbnails; never accept remote URLs or EXIF."""
import base64
import io
from .trip_service import ApiError

def validate_photo(value):
    if value is None:
        return None
    try:
        if not isinstance(value,str) or not value.startswith('data:image/jpeg;base64,') or len(value)>60000:
            raise ValueError('format or size')
        raw=base64.b64decode(value.split(',',1)[1],validate=True)
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            if image.format!='JPEG' or not 1<=image.width<=256 or not 1<=image.height<=256:
                raise ValueError('dimensions')
            image.load()
            clean=image.convert('RGB')
            clean.thumbnail((128,128))
            out=io.BytesIO()
            clean.save(out,format='JPEG',quality=75)
        return 'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode('ascii')
    except Exception:
        raise ApiError(400,'invalid_profile_photo','사진을 다시 선택해주세요. 작은 JPG 사진만 저장할 수 있어요.') from None
