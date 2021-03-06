from cellfie import utils
import glob
import numpy as np
import os
from tqdm import tqdm
import multiprocessing as mp
import time
import yaml


# load configurations
with open('config.yaml', 'r') as f:
    cfg_global = yaml.safe_load(f)
with open(os.path.join('prepare_training_data', 'config.yaml'), 'r') as f:
    cfg = yaml.safe_load(f)


def get_batch(b, batch_inds, summary_frames, folder):  # # batch, batch_inds, summary_frames, folder

    img_stack = utils.get_frames(folder, frame_inds=np.arange(batch_inds[b], batch_inds[b] + summary_frames))
    X = dict()
    X['mean'] = np.mean(img_stack, 0)
    X['median'] = np.median(img_stack, 0)
    X['max'] = np.max(img_stack, 0)
    X['std'] = np.std(img_stack, 0)
    X['corr'] = utils.get_correlation_image(img_stack)

    return X


if __name__ == '__main__':
    for d in cfg['datasets']:

        # get summary images
        folder = os.path.join(cfg_global['data_dir'], 'datasets', 'images_' + d)
        total_frames = len(glob.glob(os.path.join(folder, '*.tif*')))
        summary_frames = min(cfg['summary_frames'],
                             total_frames)  # make sure we don't look for more frames than exist in the dataset
        batch_inds = np.arange(0, total_frames, summary_frames)
        batches = min(total_frames // summary_frames, cfg['max_batches'])

        print('preparing training data for %s... (%i batches)' % (d, batches))
        start_time = time.time()

        # get summary images
        if cfg['parallelize']:
            pool = mp.Pool(cfg['cores'])
            args = [(b, batch_inds, summary_frames, folder) for b in range(batches)]  # arguments for
            X_temp = pool.starmap(get_batch, args)
            X_temp = list(X_temp)
        else:
            X_temp = [get_batch(b, batch_inds, summary_frames, folder) for b in tqdm(range(batches))]

        # stitch together batches
        X = dict()
        X['corr'] = np.array([X_temp[b]['corr'] for b in range(batches)])
        X['mean'] = np.array([X_temp[b]['mean'] for b in range(batches)])
        X['median'] = np.array([X_temp[b]['median'] for b in range(batches)])
        X['max'] = np.array([X_temp[b]['max'] for b in range(batches)])
        X['std'] = np.array([X_temp[b]['std'] for b in range(batches)])

        # collapse across summary images and scale from 0-1
        X['corr'] = utils.scale_img(np.max(X['corr'], 0))
        X['mean'] = utils.scale_img(np.max(X['mean'], 0))
        X['median'] = utils.scale_img(np.max(X['median'], 0))
        X['max'] = utils.scale_img(np.max(X['max'], 0))
        X['std'] = utils.scale_img(np.max(X['std'], 0))

        # get targets
        label_folder = os.path.join(cfg_global['data_dir'], 'labels', d)
        y = utils.get_targets(label_folder, collapse_masks=True, use_curated_labels=cfg_global['use_curated_labels'],
                              centroid_radius=cfg['centroid_radius'], border_thickness=cfg['border_thickness'])

        # get tensor of masks for each individual neuron (used by segmentation network only)
        neuron_masks = utils.get_targets(label_folder, collapse_masks=False, use_curated_labels=cfg_global['use_curated_labels'])
        neuron_masks = neuron_masks['somas']  # keep only the soma masks

        # store data for model training
        training_data_folder = os.path.join(cfg_global['data_dir'], 'training_data')
        if not os.path.exists(training_data_folder):
            os.makedirs(training_data_folder)
        np.savez(os.path.join(training_data_folder, d),
                 X=X, y=y, neuron_masks=neuron_masks, cfg_global=cfg_global, cfg=cfg)

        print('%s finished in %.1f minutes' % (d, (time.time()-start_time)/60))

    # write sample images to disk
    utils.write_sample_imgs(X_contrast=(1, 99))
    utils.write_sample_border_imgs(channels=['corr', 'median'], contrast=(1, 99))
    print('all done!')


