import os

import numpy as np
import tensorflow as tf
from absl import app, flags, logging

from retinanet.dataset_utils.mapillary_parser import MapillaryParser
from retinanet.dataset_utils.tfrecord_writer import TFrecordWriter

flags.DEFINE_string('download_path',
                    default=None,
                    help='Path to the downloaded and unzipped COCO files')

flags.DEFINE_integer('num_shards',
                     default=256,
                     help='Number of tfrecord files required')

flags.DEFINE_integer('resize_max_side',
                     default=0,
                     help='Resize max side of the image to this value')

flags.DEFINE_string('output_dir',
                    default='./mapillary_tfrecords',
                    help='Path to store the generated tfrecords in')

flags.DEFINE_boolean('check_bad_images',
                     default=False,
                     help='Check for corrupt images')


flags.DEFINE_boolean('only_val',
                     default=False,
                     help='Only generate tfrecords for validation split')


flags.DEFINE_boolean('skip_ambiguous',
                     default=False,
                     help='Skip annotations which are marked as ambiguous')

flags.DEFINE_boolean('discard_classes',
                     default=False,
                     help='Ignore classes, assign all objects `class_id=1`')

flags.DEFINE_boolean('only_dump_parsed_dataset',
                     default=False,
                     help='Skip creating tfrecords, dump parsed dataset only')

FLAGS = flags.FLAGS


def write_tfrecords(
        data,
        num_shards,
        output_dir,
        split_name,
        resize_max_side=0,
        check_bad_images=False):

    if resize_max_side:
        logging.warning('Resize max side images to {}'.format(resize_max_side))

    tfrecord_writer = TFrecordWriter(n_samples=len(data),
                                     n_shards=num_shards,
                                     output_dir=output_dir,
                                     prefix=split_name)
    bad_samples = 0
    for sample in data:
        try:
            with tf.io.gfile.GFile(sample['image'], 'rb') as fp:
                image = fp.read()

            if check_bad_images:
                _ = tf.image.decode_image(image).shape.as_list()

            if resize_max_side:
                h = sample['image_height']
                w = sample['image_width']

                if max(h, w) > resize_max_side:
                    scale = resize_max_side / max(h, w)

                    image_decoded = tf.image.decode_image(image)

                    new_h = int(h * scale)
                    new_w = int(w * scale)

                    image_decoded = tf.image.resize(
                        image_decoded,
                        size=[new_h, new_w])

                    image = tf.image.encode_jpeg(
                        tf.cast(image_decoded, dtype=tf.uint8)).numpy()

        except Exception:
            bad_samples += 1
            continue

        tfrecord_writer.push(
            image,
            np.array(sample['label']['boxes'], dtype=np.float32),
            np.array(sample['label']['classes'], dtype=np.int32),
            sample['image_id'])

    tfrecord_writer.flush_last()
    logging.warning('Skipped {} corrupted samples from {} data'.format(
        bad_samples, split_name))


def main(_):
    if not os.path.exists(FLAGS.output_dir):
        os.mkdir(FLAGS.output_dir)

    mapillary_parser = MapillaryParser(
        FLAGS.download_path,
        skip_ambiguous=FLAGS.skip_ambiguous,
        discard_classes=FLAGS.discard_classes,
        only_val=FLAGS.only_val)

    mapillary_parser.dump_parsed_dataset()

    if FLAGS.only_dump_parsed_dataset:
        return

    write_tfrecords(
        mapillary_parser.dataset['train'],
        FLAGS.num_shards,
        FLAGS.output_dir,
        'train',
        FLAGS.resize_max_side,
        FLAGS.check_bad_images)

    write_tfrecords(
        mapillary_parser.dataset['val'],
        32,
        FLAGS.output_dir,
        'val',
        FLAGS.resize_max_side,
        FLAGS.check_bad_images)


if __name__ == '__main__':
    app.run(main)
