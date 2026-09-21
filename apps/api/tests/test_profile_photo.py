import base64,io,unittest
from PIL import Image
from services.profile_photo import validate_photo
from services.trip_service import ApiError

class ProfilePhotoTests(unittest.TestCase):
    def encoded(self,size=(128,128),fmt='JPEG'):
        out=io.BytesIO();Image.new('RGB',size,'green').save(out,format=fmt)
        return 'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()
    def test_thumbnail_and_removal(self):
        result=validate_photo(self.encoded((256,256)))
        image=Image.open(io.BytesIO(base64.b64decode(result.split(',')[1])))
        self.assertEqual(image.size,(128,128));self.assertEqual(image.format,'JPEG')
        self.assertEqual(dict(image.getexif()),{});self.assertIsNone(validate_photo(None))
    def test_rejects_remote_malformed_large_and_wrong_format(self):
        for value in ['https://example.com/avatar.jpg','data:image/jpeg;base64,@@@','x'*60001,self.encoded((257,128)),self.encoded(fmt='PNG'),{},3]:
            with self.subTest(value=str(value)[:40]),self.assertRaises(ApiError): validate_photo(value)

if __name__=='__main__': unittest.main()
