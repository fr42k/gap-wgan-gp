"""
Multilayer VAE + Pixel CNN
Ishaan Gulrajani
"""

import os, sys
if 'ISHAAN_NN_LIB' in os.environ:
    sys.path.append(os.environ['ISHAAN_NN_LIB'])
else:
    sys.path.append(os.getcwd())

N_GPUS = 1

try: # This only matters on Ishaan's computer
    import experiment_tools
    experiment_tools.wait_for_gpu(tf=True, n_gpus=N_GPUS, skip=[3])
except ImportError:
    pass

import tflib as lib
import tflib.debug
import tflib.train_loop_2
import tflib.ops.kl_unit_gaussian
import tflib.ops.kl_gaussian_gaussian
import tflib.ops.conv2d
import tflib.ops.deconv2d
import tflib.ops.linear
import tflib.ops.batchnorm
import tflib.ops.embedding

import tflib.lsun_bedrooms
import tflib.mnist_256
import tflib.small_imagenet

import numpy as np
import tensorflow as tf
import scipy.misc
from scipy.misc import imsave

import time
import functools


def get_receptive_area(h,w, receptive_field, i, j):
    if i < receptive_field:
        i_min = 0
        i_end = 2*receptive_field + 1
        i_res = i
    elif i >= (h - receptive_field):
        i_end = h
        i_min = h - (2*receptive_field + 1)
        i_res = i - i_min
    else:
        i_min = i - receptive_field
        i_end = i + receptive_field + 1
        i_res = i - i_min

    if j < receptive_field:
        j_min = 0
        j_end = 2*receptive_field + 1
        j_res = j
    elif j >= (w - receptive_field):
        j_end = w
        j_min = w - (2*receptive_field + 1)
        j_res = j - j_min
    else:
        j_min = j - receptive_field
        j_end = j + receptive_field + 1
        j_res = j - j_min

    return i_min, i_end, i_res, j_min, j_end, j_res

DATASET = 'lsun_64' # mnist_256, lsun_32, lsun_64, imagenet_64
SETTINGS = '64px' # mnist_256, 32px_small, 32px_big, 64px

if SETTINGS == 'mnist_256':
    # two_level uses Enc1/Dec1 for the bottom level, Enc2/Dec2 for the top level
    # one_level uses EncFull/DecFull for the bottom (and only) level
    MODE = 'one_level'

    EMBED_INPUTS = True

    # Turn on/off the bottom-level PixelCNN in Dec1/DecFull
    PIXEL_LEVEL_PIXCNN = True
    HIGHER_LEVEL_PIXCNN = True
    PIXCNN_ONLY = False

    # These settings are good for a 'smaller' model that trains (up to 200K iters)
    # in ~1 day on a GTX 1080 (probably equivalent to 2 K40s).
    DIM_PIX_1    = 32
    DIM_1        = 16
    DIM_2        = 32
    DIM_3        = 32
    # LATENT_DIM_1 = 32
    # DIM_PIX_2    = 32

    DIM_4        = 64
    DIM_5        = 128
    LATENT_DIM_2 = 2

    ALPHA1_ITERS = 10000
    # ALPHA2_ITERS = 5000
    KL_PENALTY = 1.05
    BETA_ITERS = 1000

    # In Dec2, we break each spatial location into N blocks (analogous to channels
    # in the original PixelCNN) and model each spatial location autoregressively
    # as P(x)=P(x0)*P(x1|x0)*P(x2|x0,x1)... In my experiments values of N > 1
    # actually hurt performance. Unsure why; might be a bug.
    PIX_2_N_BLOCKS = 1

    TIMES = {
        'mode': 'iters',
        'print_every': 2*500,
        'test_every': 2*500,
        'stop_after': 500*500,
        'callback_every': 10*500
    }

    VANILLA = False
    LR = 1e-3


    LR_DECAY_AFTER = TIMES['stop_after']
    LR_DECAY_FACTOR = 1.


    BATCH_SIZE = 100
    N_CHANNELS = 1
    HEIGHT = 28
    WIDTH = 28
    LATENTS1_HEIGHT = 7
    LATENTS1_WIDTH = 7

elif SETTINGS == '32px_small':
    # two_level uses Enc1/Dec1 for the bottom level, Enc2/Dec2 for the top level
    # one_level uses EncFull/DecFull for the bottom (and only) level
    MODE = 'two_level'

    EMBED_INPUTS = False

    # Turn on/off the bottom-level PixelCNN in Dec1/DecFull
    PIXEL_LEVEL_PIXCNN = True
    HIGHER_LEVEL_PIXCNN = True
    PIXCNN_ONLY = False

    # These settings are good for a 'smaller' model that trains (up to 200K iters)
    # in ~1 day on a GTX 1080 (probably equivalent to 2 K40s).
    DIM_PIX_1    = 128
    DIM_1        = 64
    DIM_2        = 128
    DIM_3        = 256
    LATENT_DIM_1 = 64
    DIM_PIX_2    = 512

    DIM_4        = 512
    DIM_5        = 2048
    LATENT_DIM_2 = 512

    ALPHA1_ITERS = 5000
    ALPHA2_ITERS = 5000
    KL_PENALTY = 1.00
    SQUARE_ALPHA = False
    BETA_ITERS = 1000

    # In Dec2, we break each spatial location into N blocks (analogous to channels
    # in the original PixelCNN) and model each spatial location autoregressively
    # as P(x)=P(x0)*P(x1|x0)*P(x2|x0,x1)... In my experiments values of N > 1
    # actually hurt performance. Unsure why; might be a bug.
    PIX_2_N_BLOCKS = 1

    TIMES = {
        'mode': 'iters',
        'print_every': 1000,
        'test_every': 1000,
        'stop_after': 200000,
        'callback_every': 20000
    }

    VANILLA = False
    LR = 1e-3

    LR_DECAY_AFTER = 180000
    LR_DECAY_FACTOR = 1e-1


    BATCH_SIZE = 64
    N_CHANNELS = 3
    HEIGHT = 32
    WIDTH = 32

    LATENTS1_HEIGHT = 8
    LATENTS1_WIDTH = 8

elif SETTINGS == '32px_big':

    # two_level uses Enc1/Dec1 for the bottom level, Enc2/Dec2 for the top level
    # one_level uses EncFull/DecFull for the bottom (and only) level
    MODE = 'two_level'

    EMBED_INPUTS = False

    # Turn on/off the bottom-level PixelCNN in Dec1/DecFull
    PIXEL_LEVEL_PIXCNN = True
    HIGHER_LEVEL_PIXCNN = True
    PIXCNN_ONLY = False

    # These settings are good for a 'smaller' model that trains (up to 200K iters)
    # in ~1 day on a GTX 1080 (probably equivalent to 2 K40s).
    DIM_PIX_1    = 256
    DIM_1        = 128
    DIM_2        = 256
    DIM_3        = 512
    LATENT_DIM_1 = 128
    DIM_PIX_2    = 1024

    DIM_4        = 1024
    DIM_5        = 2048
    LATENT_DIM_2 = 512

    ALPHA1_ITERS = 5000
    ALPHA2_ITERS = 5000
    KL_PENALTY = 1.00
    SQUARE_ALPHA = False
    BETA_ITERS = 1000

    # In Dec2, we break each spatial location into N blocks (analogous to channels
    # in the original PixelCNN) and model each spatial location autoregressively
    # as P(x)=P(x0)*P(x1|x0)*P(x2|x0,x1)... In my experiments values of N > 1
    # actually hurt performance. Unsure why; might be a bug.
    PIX_2_N_BLOCKS = 1

    TIMES = {
        'mode': 'iters',
        'print_every': 1000,
        'test_every': 1000,
        'stop_after': 300000,
        'callback_every': 20000
    }

    VANILLA = False
    LR = 5e-4

    LR_DECAY_AFTER = 250000
    LR_DECAY_FACTOR = 2e-1

    BATCH_SIZE = 64
    N_CHANNELS = 3
    HEIGHT = 32
    WIDTH = 32
    LATENTS1_HEIGHT = 8
    LATENTS1_WIDTH = 8


elif SETTINGS == '64px':
    # WARNING! Some parts of the network architecture have hardcoded checks for
    # (SETTTINGS == '64px'), so if you just copy these settings under a new
    # label things will be different! TODO maybe fix this eventually.

    # two_level uses Enc1/Dec1 for the bottom level, Enc2/Dec2 for the top level
    # one_level uses EncFull/DecFull for the bottom (and only) level
    MODE = 'two_level'

    EMBED_INPUTS = True

    # Turn on/off the bottom-level PixelCNN in Dec1/DecFull
    PIXEL_LEVEL_PIXCNN = True
    HIGHER_LEVEL_PIXCNN = True

    DIM_EMBED    = 16
    DIM_PIX_1    = 256
    DIM_0        = 128
    DIM_1        = 256
    DIM_2        = 512
    DIM_3        = 512
    LATENT_DIM_1 = 64
    DIM_PIX_2    = 512

    DIM_4        = 512
    LATENT_DIM_2 = 512

    PIXCNN_ONLY = False
    # Uncomment for PixelCNN only (NO VAE)
    # print "WARNING PIXCNN ONLY"
    # PIXCNN_ONLY = True
    # DIM_PIX_1    = 128
    # PIX1_FILT_SIZE = 3

    # In Dec2, we break each spatial location into N blocks (analogous to channels
    # in the original PixelCNN) and model each spatial location autoregressively
    # as P(x)=P(x0)*P(x1|x0)*P(x2|x0,x1)... In my experiments values of N > 1
    # actually hurt performance. Unsure why; might be a bug.
    PIX_2_N_BLOCKS = 1

    TIMES = {
        'mode': 'iters',
        'print_every': 1,
        'test_every': 10000,
        'stop_after': 400000,
        'callback_every': 50000
    }

    VANILLA = False
    LR = 3e-4

    LR_DECAY_AFTER = 250000
    LR_DECAY_FACTOR = .5

    ALPHA1_ITERS = 5000
    ALPHA2_ITERS = 20000
    KL_PENALTY = 1.01
    BETA_ITERS = 1000

    BATCH_SIZE = 63
    N_CHANNELS = 3
    HEIGHT = 64
    WIDTH = 64
    LATENTS1_WIDTH = 8
    LATENTS1_HEIGHT = 8


if DATASET == 'mnist_256':
    train_data, dev_data, test_data = lib.mnist_256.load(BATCH_SIZE, BATCH_SIZE)
elif DATASET == 'lsun_32':
    train_data, dev_data = lib.lsun_bedrooms.load(BATCH_SIZE, downsample=True)
elif DATASET == 'lsun_64':
    train_data, dev_data = lib.lsun_bedrooms.load(BATCH_SIZE, downsample=False)
elif DATASET == 'imagenet_64':
    train_data, dev_data = lib.small_imagenet.load(BATCH_SIZE)

lib.print_model_settings(locals().copy())

DEVICES = ['/gpu:{}'.format(i) for i in xrange(N_GPUS)]

lib.ops.conv2d.enable_default_weightnorm()
lib.ops.deconv2d.enable_default_weightnorm()
lib.ops.linear.enable_default_weightnorm()

def nonlinearity(x):
    return tf.nn.elu(x)

def pixcnn_gated_nonlinearity(a, b):
    return tf.sigmoid(a) * tf.tanh(b)

def SubpixelConv2D(*args, **kwargs):
    kwargs['output_dim'] = 4*kwargs['output_dim']
    output = lib.ops.conv2d.Conv2D(*args, **kwargs)
    output = tf.transpose(output, [0,2,3,1])
    output = tf.depth_to_space(output, 2)
    output = tf.transpose(output, [0,3,1,2])
    return output

def ResidualBlock(name, input_dim, output_dim, inputs, inputs_stdev, filter_size, mask_type=None, resample=None, he_init=True):
    """
    resample: None, 'down', or 'up'
    """
    if mask_type != None and resample != None:
        raise Exception('Unsupported configuration')

    if resample=='down':
        conv_shortcut = functools.partial(lib.ops.conv2d.Conv2D, stride=2)
        conv_1        = functools.partial(lib.ops.conv2d.Conv2D, input_dim=input_dim, output_dim=input_dim)
        conv_2        = functools.partial(lib.ops.conv2d.Conv2D, input_dim=input_dim, output_dim=output_dim, stride=2)
    elif resample=='up':
        conv_shortcut = SubpixelConv2D
        conv_1        = functools.partial(SubpixelConv2D, input_dim=input_dim, output_dim=output_dim)
        conv_2        = functools.partial(lib.ops.conv2d.Conv2D, input_dim=output_dim, output_dim=output_dim)
    elif resample==None:
        conv_shortcut = lib.ops.conv2d.Conv2D
        conv_1        = functools.partial(lib.ops.conv2d.Conv2D, input_dim=input_dim,  output_dim=output_dim)
        conv_2        = functools.partial(lib.ops.conv2d.Conv2D, input_dim=output_dim, output_dim=output_dim)
    else:
        raise Exception('invalid resample value')

    if output_dim==input_dim and resample==None:
        shortcut = inputs # Identity skip-connection
    else:
        shortcut = conv_shortcut(name+'.Shortcut', input_dim=input_dim, output_dim=output_dim, filter_size=1, mask_type=mask_type, he_init=False, biases=False, inputs=inputs)

    output = inputs
    if mask_type == None:
        output = nonlinearity(output)
        output = conv_1(name+'.Conv1', filter_size=filter_size, mask_type=mask_type, inputs=output, he_init=he_init)
        output = nonlinearity(output)
        output = conv_2(name+'.Conv2', filter_size=filter_size, mask_type=mask_type, inputs=output, he_init=he_init)
    else:
        output = nonlinearity(output)
        output_a = conv_1(name+'.Conv1A', filter_size=filter_size, mask_type=mask_type, inputs=output, he_init=he_init)
        output_b = conv_1(name+'.Conv1B', filter_size=filter_size, mask_type=mask_type, inputs=output, he_init=he_init)
        output = pixcnn_gated_nonlinearity(output_a, output_b)
        output = conv_2(name+'.Conv2', filter_size=filter_size, mask_type=mask_type, inputs=output, he_init=he_init)

    return shortcut + (0.3 * output)

def Enc1(images):
    if PIXCNN_ONLY:
        batch_size = tf.shape(images)[0]
        return tf.zeros(tf.pack([batch_size, 2*LATENT_DIM_1, LATENTS1_WIDTH, LATENTS1_HEIGHT]), tf.float32)

    output = images

    if SETTINGS == '64px':
        if EMBED_INPUTS:
            output = lib.ops.conv2d.Conv2D('Enc1.Input', input_dim=N_CHANNELS*DIM_EMBED, output_dim=DIM_0, filter_size=1, inputs=output, he_init=False)
            output = ResidualBlock('Enc1.InputRes0', input_dim=DIM_0, output_dim=DIM_0, filter_size=3, resample=None, inputs_stdev=1, inputs=output)
            output = ResidualBlock('Enc1.InputRes', input_dim=DIM_0, output_dim=DIM_1, filter_size=3, resample='down', inputs_stdev=1, inputs=output)
        else:
            output = lib.ops.conv2d.Conv2D('Enc1.Input', input_dim=N_CHANNELS, output_dim=DIM_1, filter_size=1, inputs=output, he_init=False)
            output = ResidualBlock('Enc1.InputRes', input_dim=DIM_1, output_dim=DIM_1, filter_size=3, resample='down', inputs_stdev=1, inputs=output)
    else:
        if EMBED_INPUTS:
            output = lib.ops.conv2d.Conv2D('Enc1.Input', input_dim=N_CHANNELS*DIM_1, output_dim=DIM_1, filter_size=1, inputs=output, he_init=False)
        else:
            output = lib.ops.conv2d.Conv2D('Enc1.Input', input_dim=N_CHANNELS, output_dim=DIM_1, filter_size=1, inputs=output, he_init=False)

    output = ResidualBlock('Enc1.Res1Pre', input_dim=DIM_1, output_dim=DIM_1, filter_size=3, resample=None, inputs_stdev=1,          inputs=output)
    output = ResidualBlock('Enc1.Res1', input_dim=DIM_1, output_dim=DIM_2, filter_size=3, resample='down', inputs_stdev=1,          inputs=output)
    output = ResidualBlock('Enc1.Res2Pre', input_dim=DIM_2, output_dim=DIM_2, filter_size=3, resample=None, inputs_stdev=1,          inputs=output)
    output = ResidualBlock('Enc1.Res2', input_dim=DIM_2, output_dim=DIM_3, filter_size=3, resample='down', inputs_stdev=np.sqrt(2), inputs=output)
    output = ResidualBlock('Enc1.Res3Pre', input_dim=DIM_3, output_dim=DIM_3, filter_size=3, resample=None, inputs_stdev=1,          inputs=output)
    output = ResidualBlock('Enc1.Res3', input_dim=DIM_3, output_dim=DIM_3, filter_size=3, resample=None,   inputs_stdev=np.sqrt(3), inputs=output)


    output = lib.ops.conv2d.Conv2D('Enc1.Out', input_dim=DIM_3, output_dim=2*LATENT_DIM_1, filter_size=1, inputs=output, he_init=False)

    return output

def Dec1(latents, images):

    if PIXCNN_ONLY:
        batch_size = tf.shape(latents)[0]
        output = tf.zeros(tf.pack([batch_size, DIM_1, HEIGHT, WIDTH]), tf.float32)
    else:
        output = tf.clip_by_value(latents, -50., 50.)
        output = lib.ops.conv2d.Conv2D('Dec1.Input', input_dim=LATENT_DIM_1, output_dim=DIM_3, filter_size=1, inputs=output, he_init=False)

        output = ResidualBlock('Dec1.Res1', input_dim=DIM_3, output_dim=DIM_3, filter_size=3, resample=None, inputs_stdev=1, inputs=output)
        output = ResidualBlock('Dec1.Res1Post', input_dim=DIM_3, output_dim=DIM_3, filter_size=3, resample=None, inputs_stdev=1, inputs=output)
        output = ResidualBlock('Dec1.Res2', input_dim=DIM_3, output_dim=DIM_2, filter_size=3, resample='up', inputs_stdev=np.sqrt(2), inputs=output)
        output = ResidualBlock('Dec1.Res2Post', input_dim=DIM_2, output_dim=DIM_2, filter_size=3, resample=None, inputs_stdev=np.sqrt(2), inputs=output)
        output = ResidualBlock('Dec1.Res3', input_dim=DIM_2, output_dim=DIM_1, filter_size=3, resample='up', inputs_stdev=np.sqrt(3), inputs=output)
        output = ResidualBlock('Dec1.Res3Post', input_dim=DIM_1, output_dim=DIM_1, filter_size=3, resample=None, inputs_stdev=np.sqrt(3), inputs=output)

        if SETTINGS == '64px':
            output = ResidualBlock('Dec1.Res4', input_dim=DIM_1, output_dim=DIM_0, filter_size=3, resample='up', inputs_stdev=np.sqrt(3), inputs=output)
            output = ResidualBlock('Dec1.Res4Post', input_dim=DIM_0, output_dim=DIM_0, filter_size=3, resample=None, inputs_stdev=np.sqrt(3), inputs=output)

    if PIXEL_LEVEL_PIXCNN:

        if EMBED_INPUTS:
            masked_images = lib.ops.conv2d.Conv2D('Dec1.Pix1', input_dim=N_CHANNELS*DIM_EMBED, output_dim=DIM_0, filter_size=5, inputs=images, mask_type=('a', N_CHANNELS), he_init=False)
        else:
            masked_images = lib.ops.conv2d.Conv2D('Dec1.Pix1', input_dim=N_CHANNELS, output_dim=DIM_1, filter_size=7, inputs=images, mask_type=('a', N_CHANNELS), he_init=False)

        # Make the stdev of output and masked_images match
        output /= np.sqrt(4)

        # Warning! Because of the masked convolutions it's very important that masked_images comes first in this concat
        output = tf.concat(1, [masked_images, output])

        if PIXCNN_ONLY:
            for i in xrange(9):
                inp_dim = (2*DIM_1 if i==0 else DIM_PIX_1)
                output = ResidualBlock('Dec1.ExtraPixCNN_'+str(i), input_dim=inp_dim, output_dim=DIM_PIX_1, filter_size=5, mask_type=('b', N_CHANNELS), inputs_stdev=1,          inputs=output)

        if SETTINGS == '64px':
            output = ResidualBlock('Dec1.Pix2Res', input_dim=2*DIM_0, output_dim=DIM_PIX_1, filter_size=3, mask_type=('b', N_CHANNELS), inputs_stdev=1, inputs=output)
            output = ResidualBlock('Dec1.Pix3Res', input_dim=DIM_PIX_1,   output_dim=DIM_PIX_1, filter_size=3, mask_type=('b', N_CHANNELS), inputs_stdev=1, inputs=output)
            output = ResidualBlock('Dec1.Pix4Res', input_dim=DIM_PIX_1,   output_dim=DIM_PIX_1, filter_size=3, mask_type=('b', N_CHANNELS), inputs_stdev=1, inputs=output)
        else:
            output = ResidualBlock('Dec1.Pix2Res', input_dim=2*DIM_1, output_dim=DIM_PIX_1, filter_size=3, mask_type=('b', N_CHANNELS), inputs_stdev=1, inputs=output)
            output = ResidualBlock('Dec1.Pix3Res', input_dim=DIM_PIX_1, output_dim=DIM_PIX_1, filter_size=1, mask_type=('b', N_CHANNELS), inputs_stdev=1, inputs=output)

        output = lib.ops.conv2d.Conv2D('Dec1.Out', input_dim=DIM_PIX_1, output_dim=256*N_CHANNELS, filter_size=1, mask_type=('b', N_CHANNELS), he_init=False, inputs=output)

    else:

        output = lib.ops.conv2d.Conv2D('Dec1.Out', input_dim=DIM_1, output_dim=256*N_CHANNELS, filter_size=1, he_init=False, inputs=output)

    return tf.transpose(
        tf.reshape(output, [-1, 256, N_CHANNELS, HEIGHT, WIDTH]),
        [0,2,3,4,1]
    )

def Enc2(latents):
    if PIXCNN_ONLY:
        batch_size = tf.shape(latents)[0]
        return tf.zeros(tf.pack([batch_size, 2*LATENT_DIM_2]), tf.float32)

    output = tf.clip_by_value(latents, -50., 50.)

    output = lib.ops.conv2d.Conv2D('Enc2.Input', input_dim=LATENT_DIM_1, output_dim=DIM_3, filter_size=1, inputs=output, he_init=False)

    output = ResidualBlock('Enc2.Res0', input_dim=DIM_3, output_dim=DIM_3, filter_size=3, resample=None, inputs_stdev=1,          he_init=True, inputs=output)
    output = ResidualBlock('Enc2.Res1Pre', input_dim=DIM_3, output_dim=DIM_3, filter_size=3, resample=None, inputs_stdev=1,          he_init=True, inputs=output)
    output = ResidualBlock('Enc2.Res1', input_dim=DIM_3, output_dim=DIM_4, filter_size=3, resample='down', inputs_stdev=1,          he_init=True, inputs=output)
    output = ResidualBlock('Enc2.Res2Pre', input_dim=DIM_4, output_dim=DIM_4, filter_size=3, resample=None,   inputs_stdev=np.sqrt(2), he_init=True, inputs=output)
    output = ResidualBlock('Enc2.Res2', input_dim=DIM_4, output_dim=DIM_4, filter_size=3, resample=None,   inputs_stdev=np.sqrt(2), he_init=True, inputs=output)

    output = tf.reshape(output, [-1, 4*4*DIM_4])
    output = lib.ops.linear.Linear('Enc2.Output', input_dim=4*4*DIM_4, output_dim=2*LATENT_DIM_2, inputs=output)

    return output

def Dec2(latents, targets):
    if PIXCNN_ONLY:
        batch_size = tf.shape(latents)[0]
        return tf.zeros(tf.pack([batch_size, 2*LATENT_DIM_1, LATENTS1_HEIGHT, LATENTS1_WIDTH]), tf.float32)

    output = tf.clip_by_value(latents, -50., 50.)
    output = lib.ops.linear.Linear('Dec2.Input', input_dim=LATENT_DIM_2, output_dim=4*4*DIM_4, inputs=output)

    output = tf.reshape(output, [-1, DIM_4, 4, 4])

    output = ResidualBlock('Dec2.Res1', input_dim=DIM_4, output_dim=DIM_4, filter_size=3, resample=None, inputs_stdev=np.sqrt(3), he_init=True, inputs=output)
    output = ResidualBlock('Dec2.Res1Post', input_dim=DIM_4, output_dim=DIM_4, filter_size=3, resample=None, inputs_stdev=np.sqrt(3), he_init=True, inputs=output)
    output = ResidualBlock('Dec2.Res3', input_dim=DIM_4, output_dim=DIM_3, filter_size=3, resample='up', inputs_stdev=np.sqrt(3), he_init=True, inputs=output)
    output = ResidualBlock('Dec2.Res3Post', input_dim=DIM_3, output_dim=DIM_3, filter_size=3, resample=None, inputs_stdev=np.sqrt(3), he_init=True, inputs=output)
    output = ResidualBlock('Dec2.Res3Post', input_dim=DIM_3, output_dim=DIM_3, filter_size=3, resample=None, inputs_stdev=np.sqrt(3), he_init=True, inputs=output)

    if HIGHER_LEVEL_PIXCNN:

        masked_targets = lib.ops.conv2d.Conv2D('Dec2.Pix1', input_dim=LATENT_DIM_1, output_dim=DIM_3, filter_size=5, mask_type=('a', PIX_2_N_BLOCKS), he_init=False, inputs=targets)

        # Make the stdev of output and masked_targets match
        output /= np.sqrt(4)

        output = tf.concat(1, [masked_targets, output])

        output = ResidualBlock('Dec2.Pix2Res', input_dim=2*DIM_3, output_dim=DIM_PIX_2, filter_size=3, mask_type=('b', PIX_2_N_BLOCKS), inputs_stdev=1, he_init=True, inputs=output)
        output = ResidualBlock('Dec2.Pix3Res', input_dim=DIM_PIX_2, output_dim=DIM_PIX_2, filter_size=3, mask_type=('b', PIX_2_N_BLOCKS), inputs_stdev=np.sqrt(2), he_init=True, inputs=output)
        output = ResidualBlock('Dec2.Pix4Res', input_dim=DIM_PIX_2, output_dim=DIM_PIX_2, filter_size=1, mask_type=('b', PIX_2_N_BLOCKS), inputs_stdev=np.sqrt(2), he_init=True, inputs=output)

        output = lib.ops.conv2d.Conv2D('Dec2.Out', input_dim=DIM_PIX_2, output_dim=2*LATENT_DIM_1, filter_size=1, mask_type=('b', PIX_2_N_BLOCKS), he_init=False, inputs=output)
    else:

        output = lib.ops.conv2d.Conv2D('Dec2.Out', input_dim=DIM_3, output_dim=2*LATENT_DIM_1, filter_size=1, mask_type=('b', PIX_2_N_BLOCKS), he_init=False, inputs=output)

    return output


with tf.Session(config=tf.ConfigProto(allow_soft_placement=True)) as session:
    total_iters = tf.placeholder(tf.int32, shape=None, name='total_iters')
    all_images = tf.placeholder(tf.int32, shape=[None, N_CHANNELS, HEIGHT, WIDTH], name='all_images')
    all_latents1 = tf.placeholder(tf.float32, shape=[None, LATENT_DIM_1, LATENTS1_HEIGHT, LATENTS1_WIDTH], name='all_latents1')

    def split(mu_and_logsig):
        mu, logsig = tf.split(1, 2, mu_and_logsig)
        # Restrict sigma to [0,1] and mu to [-2, 2]
        mu = 2. * tf.tanh(mu / 2.)
        sig = 0.5 * (tf.nn.softsign(logsig)+1)
        logsig = tf.log(sig)
        return mu, logsig, sig
 
    def clamp_logsig_and_sig(logsig, sig):
        # Early during training (see BETA_ITERS), stop sigma from going too low
        floor = 1. - tf.minimum(1., tf.cast(total_iters, 'float32') / BETA_ITERS)
        log_floor = tf.log(floor)
        return tf.maximum(logsig, log_floor), tf.maximum(sig, floor)

    split_images = tf.split(0, len(DEVICES), all_images)
    split_latents1 = tf.split(0, len(DEVICES), all_latents1)

    tower_cost = []
    tower_outputs1_sample = []

    for device, images, latents1_sample in zip(DEVICES, split_images, split_latents1):
        with tf.device(device):

            scaled_images = (tf.cast(images, 'float32') - 128.) / 64.
            if EMBED_INPUTS:
                embedded_images = lib.ops.embedding.Embedding('Embedding', 256, DIM_EMBED, images)
                embedded_images = tf.transpose(embedded_images, [0,4,1,2,3])
                embedded_images = tf.reshape(embedded_images, [-1, DIM_EMBED*N_CHANNELS, HEIGHT, WIDTH])

            if MODE == 'one_level':

                # Layer 1

                if EMBED_INPUTS:
                    mu_and_logsig1 = EncFull(embedded_images)
                else:
                    mu_and_logsig1 = EncFull(scaled_images)
                mu1, logsig1, sig1 = split(mu_and_logsig1)

                if VANILLA:
                    latents1 = mu1
                else:
                    eps = tf.random_normal(tf.shape(mu1))
                    latents1 = mu1 + (eps * sig1)

                if EMBED_INPUTS:
                    outputs1 = DecFull(latents1, embedded_images)
                else:
                    outputs1 = DecFull(latents1, scaled_images)

                reconst_cost = tf.reduce_mean(
                    tf.nn.sparse_softmax_cross_entropy_with_logits(
                        tf.reshape(outputs1, [-1, 256]),
                        tf.reshape(images, [-1])
                    )
                )

                # Assembly

                # An alpha of exactly 0 can sometimes cause inf/nan values, so we're
                # careful to avoid it.
                alpha = tf.minimum(1., tf.cast(total_iters+1, 'float32') / ALPHA1_ITERS) * KL_PENALTY

                kl_cost_1 = tf.reduce_mean(
                    lib.ops.kl_unit_gaussian.kl_unit_gaussian(
                        mu1, 
                        logsig1,
                        sig1
                    )
                )

                kl_cost_1 *= float(LATENT_DIM_2) / (N_CHANNELS * WIDTH * HEIGHT)

                if VANILLA:
                    cost = reconst_cost
                else:
                    cost = reconst_cost + (alpha * kl_cost_1)

            elif MODE == 'two_level':
                # Layer 1

                if EMBED_INPUTS:
                    mu_and_logsig1 = Enc1(embedded_images)
                else:
                    mu_and_logsig1 = Enc1(scaled_images)
                mu1, logsig1, sig1 = split(mu_and_logsig1)

                if mu1.get_shape().as_list()[2] != LATENTS1_HEIGHT:
                    raise Exception("LATENTS1_HEIGHT doesn't match mu1 shape!")
                if mu1.get_shape().as_list()[3] != LATENTS1_WIDTH:
                    raise Exception("LATENTS1_WIDTH doesn't match mu1 shape!")

                if VANILLA:
                    latents1 = mu1
                else:
                    eps = tf.random_normal(tf.shape(mu1))
                    latents1 = mu1 + (eps * sig1)

                if EMBED_INPUTS:
                    outputs1 = Dec1(latents1, embedded_images)
                    outputs1_sample = Dec1(latents1_sample, embedded_images)
                else:
                    outputs1 = Dec1(latents1, scaled_images)

                reconst_cost = tf.reduce_mean(
                    tf.nn.sparse_softmax_cross_entropy_with_logits(
                        tf.reshape(outputs1, [-1, 256]),
                        tf.reshape(images, [-1])
                    )
                )

                # Layer 2

                # No need to inject noise into the encoder, so I pass mu1
                # instead of latents1 to Enc2
                mu_and_logsig2 = Enc2(mu1)
                mu2, logsig2, sig2 = split(mu_and_logsig2)

                if VANILLA:
                    latents2 = mu2
                else:
                    eps = tf.random_normal(tf.shape(mu2))
                    latents2 = mu2 + (eps * sig2)

                outputs2 = Dec2(latents2, latents1)

                mu1_prior, logsig1_prior, sig1_prior = split(outputs2)
                logsig1_prior, sig1_prior = clamp_logsig_and_sig(logsig1_prior, sig1_prior)

                # Assembly

                # An alpha of exactly 0 can sometimes cause inf/nan values, so we're
                # careful to avoid it.
                alpha1 = tf.minimum(1., tf.cast(total_iters+1, 'float32') / ALPHA1_ITERS) * KL_PENALTY
                alpha2 = tf.minimum(1., tf.cast(total_iters+1, 'float32') / ALPHA2_ITERS) * alpha1# * KL_PENALTY

                kl_cost_1 = tf.reduce_mean(
                    lib.ops.kl_gaussian_gaussian.kl_gaussian_gaussian(
                        mu1, 
                        logsig1,
                        sig1,
                        mu1_prior,
                        logsig1_prior,
                        sig1_prior
                    )
                )

                kl_cost_2 = tf.reduce_mean(
                    lib.ops.kl_unit_gaussian.kl_unit_gaussian(
                        mu2, 
                        logsig2,
                        sig2
                    )
                )

                kl_cost_1 *= float(LATENT_DIM_1 * LATENTS1_WIDTH * LATENTS1_HEIGHT) / (N_CHANNELS * WIDTH * HEIGHT)
                kl_cost_2 *= float(LATENT_DIM_2) / (N_CHANNELS * WIDTH * HEIGHT)

                if VANILLA:
                    cost = reconst_cost
                else:
                    cost = reconst_cost + (alpha1 * kl_cost_1) + (alpha2 * kl_cost_2)

            tower_cost.append(cost)
            tower_outputs1_sample.append(outputs1_sample)

    full_cost = tf.reduce_mean(
        tf.concat(0, [tf.expand_dims(x, 0) for x in tower_cost]), 0
    )

    full_outputs1_sample = tf.concat(0, tower_outputs1_sample)

    # Sampling

    if MODE == 'one_level':

        ch_sym = tf.placeholder(tf.int32, shape=None)
        y_sym = tf.placeholder(tf.int32, shape=None)
        x_sym = tf.placeholder(tf.int32, shape=None)
        logits = tf.reshape(tf.slice(outputs1, tf.pack([0, ch_sym, y_sym, x_sym, 0]), tf.pack([-1, 1, 1, 1, -1])), [-1, 256])
        dec1_fn_out = tf.multinomial(logits, 1)[:, 0]
        def dec1_fn(_latents, _targets, _ch, _y, _x):
            return session.run(dec1_fn_out, feed_dict={latents1: _latents, images: _targets, ch_sym: _ch, y_sym: _y, x_sym: _x, total_iters: 99999})

        def enc_fn(_images):
            return session.run(latents1, feed_dict={images: _images, total_iters: 99999})

        sample_fn_latents1 = np.random.normal(size=(8, LATENT_DIM_2)).astype('float32')

        def generate_and_save_samples(tag):
            def color_grid_vis(X, nh, nw, save_path):
                # from github.com/Newmu
                X = X.transpose(0,2,3,1)
                h, w = X[0].shape[:2]
                img = np.zeros((h*nh, w*nw, 3))
                for n, x in enumerate(X):
                    j = n/nw
                    i = n%nw
                    img[j*h:j*h+h, i*w:i*w+w, :] = x
                imsave(save_path, img)

            print "Generating latents1"

            latents1_copied = np.zeros((64, LATENT_DIM_2), dtype='float32')
            for i in xrange(8):
                latents1_copied[i::8] = sample_fn_latents1

            samples = np.zeros(
                (64, N_CHANNELS, HEIGHT, WIDTH), 
                dtype='int32'
            )

            print "Generating samples"
            for y in xrange(HEIGHT):
                for x in xrange(WIDTH):
                    for ch in xrange(N_CHANNELS):
                        next_sample = dec1_fn(latents1_copied, samples, ch, y, x)
                        samples[:,ch,y,x] = next_sample

            print "Saving samples"
            color_grid_vis(
                samples, 
                8, 
                8, 
                'samples_{}.png'.format(tag)
            )


    elif MODE == 'two_level':

        def Embed(_images):
            embedded_images = lib.ops.embedding.Embedding('Embedding', 256, DIM_EMBED, _images)
            embedded_images = tf.transpose(embedded_images, [0,4,1,2,3])
            embedded_images = tf.reshape(embedded_images, tf.pack([-1, DIM_EMBED*N_CHANNELS, tf.shape(_images)[2], tf.shape(_images)[3]]))
            return embedded_images

        def Dec1_upsample(latents):
            output = tf.clip_by_value(latents, -50., 50.)
            output = lib.ops.conv2d.Conv2D('Dec1.Input', input_dim=LATENT_DIM_1, output_dim=DIM_3, filter_size=1, inputs=output, he_init=False)

            output = ResidualBlock('Dec1.Res1', input_dim=DIM_3, output_dim=DIM_3, filter_size=3, resample=None, inputs_stdev=1, inputs=output)
            output = ResidualBlock('Dec1.Res1Post', input_dim=DIM_3, output_dim=DIM_3, filter_size=3, resample=None, inputs_stdev=1, inputs=output)
            output = ResidualBlock('Dec1.Res2', input_dim=DIM_3, output_dim=DIM_2, filter_size=3, resample='up', inputs_stdev=np.sqrt(2), inputs=output)
            output = ResidualBlock('Dec1.Res2Post', input_dim=DIM_2, output_dim=DIM_2, filter_size=3, resample=None, inputs_stdev=np.sqrt(2), inputs=output)
            output = ResidualBlock('Dec1.Res3', input_dim=DIM_2, output_dim=DIM_1, filter_size=3, resample='up', inputs_stdev=np.sqrt(3), inputs=output)
            output = ResidualBlock('Dec1.Res3Post', input_dim=DIM_1, output_dim=DIM_1, filter_size=3, resample=None, inputs_stdev=np.sqrt(3), inputs=output)

            output = ResidualBlock('Dec1.Res4', input_dim=DIM_1, output_dim=DIM_0, filter_size=3, resample='up', inputs_stdev=np.sqrt(3), inputs=output)
            output = ResidualBlock('Dec1.Res4Post', input_dim=DIM_0, output_dim=DIM_0, filter_size=3, resample=None, inputs_stdev=np.sqrt(3), inputs=output)

            # Make the stdev of output and masked_images match
            output /= np.sqrt(4)
            return output

        def Dec1_pixel(upsampled_z1, _targets):
            if PIXEL_LEVEL_PIXCNN:
                masked_images = lib.ops.conv2d.Conv2D('Dec1.Pix1', input_dim=N_CHANNELS*DIM_EMBED, output_dim=DIM_0, filter_size=5, inputs=_targets, mask_type=('a', N_CHANNELS), he_init=False)

                # Warning! Because of the masked convolutions it's very important that masked_images comes first in this concat
                output = tf.concat(1, [masked_images, upsampled_z1])

                print upsampled_z1.get_shape().as_list(), masked_images.get_shape().as_list()
                output = ResidualBlock('Dec1.Pix2Res', input_dim=2*DIM_0, output_dim=DIM_PIX_1, filter_size=3, mask_type=('b', N_CHANNELS), inputs_stdev=1, inputs=output)
                output = ResidualBlock('Dec1.Pix3Res', input_dim=DIM_PIX_1,   output_dim=DIM_PIX_1, filter_size=3, mask_type=('b', N_CHANNELS), inputs_stdev=1, inputs=output)
                output = ResidualBlock('Dec1.Pix4Res', input_dim=DIM_PIX_1,   output_dim=DIM_PIX_1, filter_size=3, mask_type=('b', N_CHANNELS), inputs_stdev=1, inputs=output)
                output = lib.ops.conv2d.Conv2D('Dec1.Out', input_dim=DIM_PIX_1, output_dim=256*N_CHANNELS, filter_size=1, mask_type=('b', N_CHANNELS), he_init=False, inputs=output)
            else:
                output = lib.ops.conv2d.Conv2D('Dec1.Out', input_dim=DIM_1, output_dim=256*N_CHANNELS, filter_size=1, he_init=False, inputs=output)

            return tf.transpose(
                tf.reshape(output, tf.pack([-1, 256, N_CHANNELS, tf.shape(_targets)[2], tf.shape(_targets)[3]])),
                [0,2,3,4,1]
            )

        latents_sym = tf.placeholder(tf.float32, shape = [None, LATENT_DIM_1, None, None], name = 'latents_sym')
        upsample_this_thing = Dec1_upsample(latents_sym)
        def upsample_dec1(_latents):
            return session.run(upsample_this_thing, feed_dict={latents_sym:_latents, total_iters:99999})

        images_sym = tf.placeholder(tf.int32, shape = [None, N_CHANNELS, None, None], name = 'images_sym')
        upsampled_latents_sym = tf.placeholder(tf.float32, shape = [None, DIM_0, None, None], name = 'upsampled_latents_sym')
        logit_this_thing = Dec1_pixel(upsampled_latents_sym, Embed(images_sym))
        def dec1_logits_fn(_upsampled_latents, _images):
            return session.run(logit_this_thing, feed_dict={upsampled_latents_sym:_upsampled_latents, images_sym:_images})

        ##########################################
        tf.train.Saver().restore(session, '/Tmp/ahmedfar/LSUN64/resnet_lsun64_big_params.ckpt')

        def dec2_fn(_latents, _targets):
            return session.run([mu1_prior, logsig1_prior], feed_dict={latents2: _latents, latents1: _targets, total_iters: 99999})

        N_SAMPLES = 36
        if N_SAMPLES % N_GPUS != 0:
            raise Exception("N_SAMPLES must be divisible by N_GPUS")

        HOLD_Z2_CONSTANT = False
        HOLD_EPSILON_1_CONSTANT = False
        HOLD_EPSILON_PIXELS_CONSTANT = False

        # Draw z2 from N(0,I)
        z2 = np.random.normal(size=(N_SAMPLES, LATENT_DIM_2)).astype('float32')
        if HOLD_Z2_CONSTANT:
          z2[:] = z2[0][None]

        # Draw epsilon_1 from N(0,I)
        epsilon_1 = np.random.normal(size=(N_SAMPLES, LATENT_DIM_1, LATENTS1_HEIGHT, LATENTS1_WIDTH)).astype('float32')
        if HOLD_EPSILON_1_CONSTANT:
          epsilon_1[:] = epsilon_1[0][None]

        # Draw epsilon_pixels from U[0,1]
        epsilon_pixels = np.random.uniform(size=(N_SAMPLES, N_CHANNELS, HEIGHT, WIDTH))
        if HOLD_EPSILON_PIXELS_CONSTANT:
          epsilon_pixels[:] = epsilon_pixels[0][None]

        def generate_and_save_samples(tag, TEMPERATURE):
            # Draw z1 autoregressively using z2 and epsilon1
            print "Generating z1"
            z1 = np.zeros((N_SAMPLES, LATENT_DIM_1, LATENTS1_HEIGHT, LATENTS1_WIDTH), dtype='float32')
            for y in xrange(LATENTS1_HEIGHT):
              for x in xrange(LATENTS1_WIDTH):
                z1_prior_mu, z1_prior_logsig = dec2_fn(z2, z1)
                z1[:,:,y,x] = z1_prior_mu[:,:,y,x] + np.exp(z1_prior_logsig[:,:,y,x]) * epsilon_1[:,:,y,x]

            # Draw pixels (the images) autoregressively using z1 and epsilon_x
            print "Generating pixels"
            pixels = np.zeros((N_SAMPLES, N_CHANNELS, HEIGHT, WIDTH)).astype('int32')
            _upsampled_latents = upsample_dec1(z1)
            
            RECEPTIVE_FIELD_z1 = 8
            for j in xrange(HEIGHT):
                print j, 'of', HEIGHT
                t0 = time.time()
                for k in xrange(WIDTH):
                    for i in xrange(N_CHANNELS):
                        j_min, j_end, j_res, k_min, k_end, k_res = get_receptive_area(HEIGHT, WIDTH, RECEPTIVE_FIELD_z1, j,k)
                        pixels_slice = pixels[:, :, j_min:j_end, k_min:k_end]
                        latents1_slice = _upsampled_latents[:, :, j_min:j_end, k_min:k_end]
                        logits = dec1_logits_fn(latents1_slice, pixels_slice)[:,i,j_res,k_res]/TEMPERATURE

                        probs = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
                        probs = probs / np.sum(probs, axis=-1, keepdims=True)
                        cdf = np.cumsum(probs, axis=-1)
                        pixels[:,i, j, k] = np.argmax(cdf >= epsilon_pixels[:,i,j,k,None], axis=-1)
                print 'this took', time.time()-t0, 'seconds'

            # Save them
            def color_grid_vis(X, nh, nw, save_path):
                # from github.com/Newmu
                X = X.transpose(0,2,3,1)
                h, w = X[0].shape[:2]
                img = np.zeros((h*nh, w*nw, 3))
                for n, x in enumerate(X):
                    j = n/nw
                    i = n%nw
                    img[j*h:j*h+h, i*w:i*w+w, :] = x
                imsave(save_path, img)

            print "Saving"
            rows = int(np.sqrt(N_SAMPLES))
            while N_SAMPLES % rows != 0:
                rows -= 1
            color_grid_vis(
                pixels, rows, N_SAMPLES/rows, 
                'samples_{}_{}.png'.format(tag, TEMPERATURE)
            )

    generate_and_save_samples('64_LSUN', 1.)
    generate_and_save_samples('64_LSUN', 0.5)
    generate_and_save_samples('64_LSUN', 0.25)
    generate_and_save_samples('64_LSUN', 0.125)

