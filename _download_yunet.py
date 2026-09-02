import urllib.request, os, sys

def log(*a):
    sys.stdout.write(' '.join(str(x) for x in a) + '\n'); sys.stdout.flush()

urls = [
    ('https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx', 'backend/cv2_yunet.onnx'),
]
dst_dir = os.path.abspath('backend')
for url, dst in urls:
    dst_path = os.path.join(dst_dir, os.path.basename(dst))
    if os.path.exists(dst_path):
        log('exists', dst_path, os.path.getsize(dst_path))
        continue
    try:
        log('downloading', url)
        urllib.request.urlretrieve(url, dst_path)
        log('downloaded', os.path.getsize(dst_path), 'bytes ->', dst_path)
    except Exception as e:
        log('download failed:', repr(e))

# Verify
try:
    import cv2
    p = os.path.join(dst_dir, 'cv2_yunet.onnx')
    log('model exists:', os.path.exists(p))
    if os.path.exists(p):
        det = cv2.FaceDetectorYN.create(p, '', (320, 320), 0.9, 0.3, 5000)
        log('FaceDetectorYN created OK')
except Exception as e:
    log('verify failed:', repr(e))
