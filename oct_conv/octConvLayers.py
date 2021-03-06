import numpy as np
from tensorflow.keras import backend as K
from tensorflow.keras.layers import Layer
from tensorflow.keras import Input, Model
from tensorflow.keras.layers import Conv2D, AveragePooling2D, UpSampling2D, add

import utils
from custom_generator import SRCNNGenerator


class OctConvInitialLayer(Layer):
    """
                Initializes the Octave Convolution architecture.
                Accepts a single input tensor, and returns a pair of tensors.
                The first tensor is the high frequency pathway.
                The second tensor is the low frequency pathway.
                # Arguments:
                    ip: keras tensor.
                    filters: number of filters in conv layer.
                    kernel_size: conv kernel size.
                    strides: strides of the conv.
                    alpha: float between [0, 1]. Defines the ratio of filters
                        allocated to the high frequency and low frequency
                        branches of the octave conv.
                    padding: padding mode.
                    dilation: dilation conv kernel.
                    bias: bool, whether to use bias or not.
                # Returns:
                    a pair of tensors:
                        - x_high: high frequency pathway.
                        - x_low: low frequency pathway.
                """
    def __init__(self, filters, kernel_size=(3, 3), strides=(1, 1),
                 alpha=0.5, padding='same', dilation=None, bias=False, activation="relu"):
        super(OctConvInitialLayer, self).__init__()
        self.strides = strides
        if dilation is None:
            dilation = (1, 1)
        high_low_filters = int(alpha * filters)
        high_high_filters = filters - high_low_filters
        self.conv2d_high_high = Conv2D(high_high_filters, kernel_size, padding=padding,
                                       dilation_rate=dilation, use_bias=bias,
                                       kernel_initializer='he_normal', activation=activation)
        self.average_pooling2d_high_low = AveragePooling2D()
        self.conv2d_high_low = Conv2D(high_low_filters, kernel_size, padding=padding,
                                      dilation_rate=dilation, use_bias=bias,
                                      kernel_initializer='he_normal', activation=activation)

    def call(self, inputs, **kwargs):
        if self.strides[0] > 1:
            inputs = AveragePooling2D()(inputs)
        x_high = self.conv2d_high_high(inputs)
        x_high_low = self.average_pooling2d_high_low(inputs)
        x_low = self.conv2d_high_low(x_high_low)
        return x_low, x_high


class OctConvBlockLayer(Layer):
    """
            Constructs an Octave Convolution block.
            Accepts a pair of input tensors, and returns a pair of tensors.
            The first tensor is the high frequency pathway for both ip/op.
            The second tensor is the low frequency pathway for both ip/op.
            # Arguments:
                self.x_high: keras tensor.
                self.x_low: keras tensor.
                filters: number of filters in conv layer.
                kernel_size: conv kernel size.
                strides: strides of the conv.
                alpha: float between [0, 1]. Defines the ratio of filters
                    allocated to the high frequency and low frequency
                    branches of the octave conv.
                padding: padding mode.
                dilation: dilation conv kernel.
                bias: bool, whether to use bias or not.
            # Returns:
                a pair of tensors:
                    - x_high: high frequency pathway.
                    - x_low: low frequency pathway.
            """
    def __init__(self, filters, kernel_size=(3, 3), strides=(1, 1),
                 alpha=0.5, padding='same', dilation=None, bias=False, activation="relu"):
        super(OctConvBlockLayer, self).__init__()
        self.strides = strides
        if dilation is None:
            dilation = (1, 1)
        low_low_filters = high_low_filters = int(alpha * filters)
        high_high_filters = low_high_filters = filters - low_low_filters
        self.conv2d_high_high = Conv2D(high_high_filters, kernel_size, padding=padding,
                                       dilation_rate=dilation, use_bias=bias,
                                       kernel_initializer='he_normal', activation=activation)
        self.conv2d_low_high = Conv2D(low_high_filters, kernel_size, padding=padding,
                                      dilation_rate=dilation, use_bias=bias,
                                      kernel_initializer='he_normal', activation=activation)
        self.upsampling2d = UpSampling2D(interpolation="nearest")
        self.conv2d_low_low = Conv2D(low_low_filters, kernel_size, padding=padding,
                                     dilation_rate=dilation, use_bias=bias,
                                     kernel_initializer='he_normal', activation=activation)
        self.conv2d_high_low = Conv2D(high_low_filters, kernel_size, padding=padding,
                                      dilation_rate=dilation, use_bias=bias,
                                      kernel_initializer='he_normal', activation=activation)
        self.average_pooling2d = AveragePooling2D()

    def call(self, inputs, **kwargs):
        x_low = inputs[0]
        x_high = inputs[1]
        if self.strides[0] > 1:
            x_high = self.average_pooling2d(x_high)
            x_low = self.average_pooling2d(x_low)
        # For High Freq outputs
        x_high_high = self.conv2d_high_high(x_high)
        x_low_high = self.conv2d_low_high(x_low)
        x_low_high = self.upsampling2d(x_low_high)
        # For Low Freq Outputs
        x_low_low = self.conv2d_low_low(x_low)
        x_high_low = self.average_pooling2d(x_high)
        x_high_low = self.conv2d_high_low(x_high_low)

        # Merge Outputs
        y_high = add([x_high_high, x_low_high])
        y_low = add([x_low_low, x_high_low])
        return y_low, y_high


class OctConvFinalLayer(Layer):
    """
            Ends the Octave Convolution architecture.
            Accepts two input tensors, and returns a single output tensor.
            The first input tensor is the high frequency pathway.
            The second input tensor is the low frequency pathway.
            # Arguments:
                self.x_high: keras tensor.
                self.x_low: keras tensor.
                filters: number of filters in conv layer.
                kernel_size: conv kernel size.
                strides: strides of the conv.
                padding: padding mode.
                dilation: dilation conv kernel.
                bias: bool, whether to use bias or not.
            # Returns:
                a single Keras tensor:
                    - x_high: The merged high frequency pathway.
            """
    def __init__(self, filters, kernel_size=(3, 3), strides=(1, 1),
                 padding='same', dilation=None, bias=False, activation="relu"):
        super(OctConvFinalLayer, self).__init__()
        self.strides = strides
        if dilation is None:
            dilation = (1, 1)
        self.average_pooling2d = AveragePooling2D()
        self.conv2d_high_high = Conv2D(filters, kernel_size, padding=padding,
                                       dilation_rate=dilation, use_bias=bias,
                                       kernel_initializer='he_normal', activation=activation)
        self.conv2d_low_high = Conv2D(filters, kernel_size, padding=padding,
                                      dilation_rate=dilation, use_bias=bias,
                                      kernel_initializer='he_normal', activation=activation)
        self.upsampling2d = UpSampling2D(interpolation="nearest")

    def call(self, inputs, **kwargs):
        x_low = inputs[0]
        x_high = inputs[1]
        if self.strides[0] > 1:
            x_high = self.average_pooling2d(x_high)
            x_low = self.average_pooling2d(x_low)
        x_high_high = self.conv2d_high_high(x_high)
        x_low_high = self.conv2d_low_high(x_low)
        x_low_high = self.upsampling2d(x_low_high)
        x = add([x_high_high, x_low_high])
        return x





