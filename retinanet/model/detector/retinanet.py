import functools

import numpy as np
import tensorflow as tf

from retinanet.core.utils import get_normalization_op
from retinanet.model.builder import DETECTOR

@DETECTOR.register_module('retinanet')
class RetinaNet(tf.keras.Model):
    """ RetinaNet detector class. """
    # TODO (kartik4949): remove params, pass needed keys.
    def __init__(self, backbone, fpn,  params, **kwargs):
        k_init = tf.keras.initializers.RandomNormal(stddev=0.01)
        b_init = tf.zeros_initializer()
        prior_prob = tf.constant_initializer(-np.log((1 - 0.01) / 0.01))
        image_inputs = tf.keras.Input(shape=backbone.input.shape[1:], name="images")

        backbone_outs = backbone(image_inputs)
        fpn_outs = fpn(backbone_outs)

        conv_2d_op = tf.keras.layers.Conv2D

        normalization_op = get_normalization_op()
        bn_op = functools.partial(
            normalization_op,
            momentum=0.997,
            epsilon=1e-4)

        relu_op = tf.keras.layers.ReLU

        conv_3x3 = functools.partial(
            conv_2d_op,
            filters=256,
            kernel_size=3,
            strides=1,
            padding='same',
            kernel_initializer=k_init,
            bias_initializer=b_init)

        conv2d_same_pad = functools.partial(
            conv_2d_op,
            kernel_size=3,
            strides=1,
            padding='same',
            kernel_initializer=tf.keras.initializers.RandomNormal(stddev=1e-5))

        class_convs = []
        box_convs = []

        for i in range(params.architecture.num_head_convs):
            class_convs += [conv_3x3(name='class-' + str(i))]
            box_convs += [conv_3x3(name='box-' + str(i))]

        box_convs += [
            conv2d_same_pad(filters=params.architecture.num_anchors * 4,
                            name='box-predictions',
                            bias_initializer=b_init,
                            dtype=tf.float32)
        ]
        class_convs += [
            conv2d_same_pad(filters=params.architecture.num_anchors * params.architecture.num_classes,  # noqa: E501
                            name='class-predictions',
                            bias_initializer=prior_prob,
                            dtype=tf.float32)
        ]

        box_bns = [
            bn_op(name='box-{}-{}'.format(i, j))
            for i in range(params.architecture.num_head_convs) for j in range(3, 8)
        ]
        class_bns = [
            bn_op(name='class-{}-{}'.format(i, j), )
            for i in range(params.architecture.num_head_convs) for j in range(3, 8)
        ]

        class_outputs = {}
        box_outputs = {}

        for i, output in enumerate(fpn_outs):
            class_x = box_x = output
            for j in range(params.architecture.num_head_convs):
                class_x = class_convs[j](class_x)
                class_x = class_bns[i + 5 * j](class_x)
                class_x = relu_op(name='p{}-class-{}-relu'.format(i, j))(class_x)
                box_x = box_convs[j](box_x)
                box_x = box_bns[i + 5 * j](box_x)
                box_x = relu_op(name='p{}-box-{}-relu'.format(i, j))(box_x)
            class_outputs[i + 3] = class_convs[-1](class_x)
            box_outputs[i + 3] = box_convs[-1](box_x)

        outputs = {
            'class-predictions': class_outputs,
            'box-predictions': box_outputs
        }
        super().__init__(inputs=image_inputs, outputs=outputs, name=params.architecture.name, **kwargs)
