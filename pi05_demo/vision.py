"""Physical camera inventory and explicit RLinf policy-slot mapping."""
import json
import numpy as np

POLICY_KEYS = ('base_0_rgb', 'left_wrist_0_rgb', 'right_wrist_0_rgb')

def camera_views(config=None):
    views = tuple((config or {}).get('views', ('main', 'wrist')))
    if views not in (('wrist',), ('main', 'wrist')):
        raise ValueError("camera views must be ['wrist'] or ['main', 'wrist']")
    return views

def episode_views(episode):
    config = json.loads(episode.attrs['config_json'])
    return camera_views(config.get('cameras'))

def policy_mapping(views):
    views = camera_views({'views': views})
    # RLinf FrankaEEInputs uses the first policy slot for its single physical view.
    return ({'base_0_rgb': 'wrist'} if views == ('wrist',) else
            {'base_0_rgb': 'main', 'left_wrist_0_rgb': 'wrist'})

def policy_images(row, views):
    mapping = policy_mapping(views)
    images = {key: np.zeros((224, 224, 3), np.uint8) for key in POLICY_KEYS}
    for key, view in mapping.items():
        value = row[f'observation.images.{view}']
        if hasattr(value, 'detach'):
            value = value.detach().cpu().numpy()
        rgb = np.asarray(value)
        if rgb.shape != (3, 224, 224):
            raise ValueError(f'{view}: expected decoded CHW RGB224')
        images[key] = np.rint(np.clip(rgb.transpose(1, 2, 0), 0, 1) * 255).astype(np.uint8)
    return images, {key: key in mapping for key in POLICY_KEYS}
