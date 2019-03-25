from keras.layers import Dense, Conv2D, Activation, Input, Flatten, AveragePooling2D, MaxPool2D, LeakyReLU, Dropout, Add
from keras.layers import BatchNormalization
from keras.models import Model, save_model
from keras.optimizers import Adam, SGD
import keras.backend as K
from keras.utils import multi_gpu_model
import numpy as np
import pandas as pd


class StandardConvNet(object):
    """
    Standard Convolutional Neural Network contains a series of convolution and pooling layers followed by one
    fully connected layer to a set of scalar outputs. The number of convolution filters is assumed to increase
    with depth.
    
    Attributes:
        min_filters (int): The number of convolution filters in the first layer. 
        filter_growth_rate (float): Multiplier on the number of convolution filters between layers.
        min_data_width (int): The minimum dimension of the input data after the final pooling layer. Constrains the number of 
            convolutional layers.
        hidden_activation (str): The nonlinear activation function applied after each convolutional layer. If "leaky", a leaky ReLU with
            alpha=0.1 is used.
        output_activation (str): The nonlinear activation function applied on the output layer.
        pooling (str): If mean, then :class:`keras.layers.AveragePooling2D` is used for pooling. If max, then :class:`keras.layers.MaxPool2D` is used.
        use_dropout (bool): If True, then a :class:`keras.layers.Dropout` layer is inserted between the final convolution block 
            and the output :class:`keras.laysers.Dense` layer.

    """
    def __init__(self, min_filters=16, filter_growth_rate=2, filter_width=5, min_data_width=4,
                 hidden_activation="relu", output_activation="sigmoid",
                 pooling="mean", use_dropout=False, dropout_alpha=0.0,
                 data_format="channels_first", optimizer="adam", loss="mse", leaky_alpha=0.1, metrics=None, 
                 learning_rate=0.00001, batch_size=256, epochs=10, verbose=0):
        self.min_filters = min_filters
        self.filter_width = filter_width
        self.filter_growth_rate = filter_growth_rate
        self.min_data_width = min_data_width
        self.hidden_activation = hidden_activation
        self.output_activation = output_activation
        self.use_dropout = use_dropout
        self.pooling = pooling
        self.dropout_alpha = dropout_alpha
        self.data_format = data_format
        self.optimizer = optimizer
        self.learning_rate = learning_rate
        self.loss = loss
        self.metrics = metrics
        self.leaky_alpha = leaky_alpha
        self.batch_size = batch_size
        self.epochs = epochs
        self.model = None
        self.parallel_model = None
        self.verbose = verbose

    def build_network(self, input_shape, output_size):
        """
        Create a keras model with the hyperparameters specified in the constructor.

        Args:
            input_shape (tuple of shape [variable, y, x]): The shape of the input data
            output_size: Number of neurons in output layer.
        """
        input_layer = Input(shape=input_shape, name="scn_input")
        num_conv_layers = int(np.log2(input_shape[1]) - np.log2(self.min_data_width))
        num_filters = self.min_filters
        scn_model = input_layer
        for c in range(num_conv_layers):
            scn_model = Conv2D(num_filters, (self.filter_width, self.filter_width),
                               data_format=self.data_format, padding="same", name="conv_{0:02d}".format(c))(scn_model)
            if self.hidden_activation == "leaky":
                scn_model = LeakyReLU(self.leaky_alpha, name="hidden_activation_{0:02d}".format(c))(scn_model)
            else:
                scn_model = Activation(self.hidden_activation, name="hidden_activation_{0:02d}".format(c))(scn_model)
            num_filters = int(num_filters * self.filter_growth_rate)
            if self.pooling.lower() == "max":
                scn_model = MaxPool2D(data_format=self.data_format, name="pooling_{0:02d}".format(c))(scn_model)
            else:
                scn_model = AveragePooling2D(data_format=self.data_format, name="pooling_{0:02d}".format(c))(scn_model)
        scn_model = Flatten(name="flatten")(scn_model)
        if self.use_dropout:
            scn_model = Dropout(self.dropout_alpha, name="dense_dropout")(scn_model)
        scn_model = Dense(output_size, name="dense_output")(scn_model)
        scn_model = Activation(self.output_activation, name="activation_output")(scn_model)
        self.model = Model(input_layer, scn_model)

    def compile_model(self):
        """
        Compile the model in tensorflow with the right optimizer and loss function.
        """
        if self.optimizer == "adam":
            opt = Adam(lr=self.learning_rate)
        else:
            opt = SGD(lr=self.learning_rate, momentum=0.99)
        self.model.compile(opt, self.loss, metrics=self.metrics)

    def compile_parallel_model(self):
        if self.optimizer == "adam":
            opt = Adam(lr=self.learning_rate)
        else:
            opt = SGD(lr=self.learning_rate, momentum=0.99)
        self.parallel_model.compile(opt, self.loss, metrics=self.metrics)

    @staticmethod
    def get_data_shapes(x, y):
        """
        Extract the input and output data shapes in order to construct the neural network.
        """
        if len(x.shape) != 4:
            raise ValueError("Input data does not have dimensions (examples, y, x, predictor)")
        if len(y.shape) == 1:
            output_size = 1
        else:
            output_size = y.shape[1]
        return x.shape[1:], output_size

    def fit(self, x, y, val_x=None, val_y=None, build=True):
        """
        Train the neural network.
        """
        if build:
            x_shape, y_size = self.get_data_shapes(x, y)
            self.build_network(x_shape, y_size)
            self.compile_model()
        if val_x is None:
            val_data = None
        else:
            val_data = (val_x, val_y)
        self.model.fit(x, y, batch_size=self.batch_size, epochs=self.epochs, verbose=self.verbose,
                       validation_data=val_data)

    def predict(self, x, y):
        return self.model.predict(x, y, batch_size=self.batch_size)


class ResNet(StandardConvNet):
    """
    Extension of the :class:`goes16ci.models.StandardConvNet` to include Residual layers instead of single convolutional layers.
    The residual layers split the data signal off, apply normalization and convolutions to it, then adds it back on to the original field.
    """
    def __init__(self, min_filters=16, filter_growth_rate=2, filter_width=5, min_data_width=4,
                 hidden_activation="relu", output_activation="sigmoid", metrics=None,
                 pooling="mean", use_dropout=False, dropout_alpha=0.0, data_format="channels_first", learning_rate=0.00001,
                 optimizer="adam", loss="mse", leaky_alpha=0.1, batch_size=256, epochs=10, verbose=0):
        super().__init__(min_filters=min_filters, filter_growth_rate=filter_growth_rate, filter_width=filter_width,
                         min_data_width=min_data_width, hidden_activation=hidden_activation, data_format=data_format,
                         output_activation=output_activation, pooling=pooling, use_dropout=use_dropout,
                         dropout_alpha=dropout_alpha, optimizer=optimizer, loss=loss, metrics=metrics, leaky_alpha=leaky_alpha,
                         batch_size=batch_size, epochs=epochs, verbose=verbose, learning_rate=learning_rate)

    def residual_block(self, filters, in_layer, layer_number=0):
        """
        Generate a single residual block.
        """
        if self.data_format == "channels_first":
            norm_axis = 1
        else:
            norm_axis = -1
        if in_layer.shape[-1].value != filters:
            x = Conv2D(filters, self.filter_width, data_format=self.data_format, padding="same")(in_layer)
        else:
            x = in_layer
        y = BatchNormalization(axis=norm_axis, name="bn_res_{0:02d}_a".format(layer_number))(x)
        if self.hidden_activation == "leaky":
            y = LeakyReLU(self.leaky_alpha, name="res_activation_{0:02d}_a".format(layer_number))(y)
        else:
            y = Activation(self.hidden_activation,
                           name="res_activation_{0:02d}_a".format(layer_number))(y)
        y = Conv2D(filters, self.filter_width, padding="same",
                   data_format=self.data_format, name="res_conv_{0:02d}_a".format(layer_number))(y)
        y = BatchNormalization(axis=norm_axis, name="bn_res_{0:02d}_b".format(layer_number))(y)
        if self.hidden_activation == "leaky":
            y = LeakyReLU(self.leaky_alpha, name="res_activation_{0:02d}_b".format(layer_number))(y)
        else:
            y = Activation(self.hidden_activation,
                           name="res_activation_{0:02d}_b".format(layer_number))(y)
        y = Conv2D(filters, self.filter_width, padding="same",
                   data_format=self.data_format, name="res_conv_{0:02d}_b".format(layer_number))(y)
        out = Add()([y, x])
        return out

    def build_network(self, input_shape, output_size):
        input_layer = Input(shape=input_shape, name="scn_input")
        num_conv_layers = int(np.log2(input_shape[1]) - np.log2(self.min_data_width))
        print(num_conv_layers)
        num_filters = self.min_filters
        res_model = input_layer
        for c in range(num_conv_layers):
            res_model = self.residual_block(num_filters, res_model, c)
            num_filters = int(num_filters * self.filter_growth_rate)
            if self.pooling.lower() == "max":
                res_model = MaxPool2D(data_format=self.data_format, name="pooling_{0:02d}".format(c))(res_model)
            else:
                res_model = AveragePooling2D(data_format=self.data_format, name="pooling_{0:02d}".format(c))(res_model)
        res_model = Flatten(name="flatten")(res_model)
        if self.use_dropout:
            res_model = Dropout(self.dropout_alpha, name="dense_dropout")(res_model)
        res_model = Dense(output_size, name="dense_output")(res_model)
        res_model = Activation(self.output_activation, name="activation_output")(res_model)
        self.model = Model(input_layer, res_model)


def train_conv_net_cpu(train_data, train_labels, val_data, val_labels,
                       conv_net_hyperparameters, num_processors, seed):
    np.random.seed(seed)
    K.tf.set_random_seed(seed)
    sess = K.tf.Session(config=K.tf.ConfigProto(allow_soft_placement=False, intra_op_parallelism_threads=1,
                                                inter_op_parallelism_threads=num_processors))
    K.set_session(sess)

    with K.tf.device("/cpu:0"):
        scn = StandardConvNet(**conv_net_hyperparameters)
        scn.fit(train_data, train_labels, val_x=val_data, val_y=val_labels)
    sess.close()
    del sess
    return


def train_conv_net_gpu(train_data, train_labels, val_data, val_labels,
                       conv_net_hyperparameters, num_gpus, seed, dtype="float32", cpu_relocation=False, cpu_merge=False):
    np.random.seed(seed)
    config = K.tf.ConfigProto(allow_soft_placement=False)
    config.gpu_options.allow_growth = True
    sess = K.tf.Session(config=config)
    K.set_session(sess)
    K.tf.set_random_seed(seed)
    K.set_floatx(dtype)
    scn = None
    if num_gpus == 1:
        with K.tf.device("/gpu:0"):
            scn = ResNet(**conv_net_hyperparameters)
            #scn = StandardConvNet(**conv_net_hyperparameters)
            scn.fit(train_data, train_labels, val_x=val_data, val_y=val_labels)
            print(scn.model.summary())
    elif num_gpus > 1:
        scn = ResNet(**conv_net_hyperparameters)
        scn.batch_size *= num_gpus
        #scn = StandardConvNet(**conv_net_hyperparameters)
        x_shape, y_size = scn.get_data_shapes(train_data, train_labels)
        scn.build_network(x_shape, y_size)
        print(scn.model.summary())
        scn.model = multi_gpu_model(scn.model, gpus=num_gpus, cpu_merge=cpu_merge, cpu_relocation=cpu_relocation)
        scn.compile_model()
        print(scn.model.summary())
        scn.fit(train_data, train_labels, val_x=val_data, val_y=val_labels)
    else:
        print("Number of GPUs set to 0")
    if scn is not None:
        save_model(scn.model, "goes16_resnet_gpus_{0:02d}.h5".format(num_gpus))
    sess.close()
    del sess
    return


class MinMaxScaler2D(object):
    """
    Rescale input arrays of shape (examples, y, x, variable) to range from out_min to out_max.

    """
    def __init__(self, out_min=0, out_max=1, scale_values=None):
        self.out_min = out_min
        self.out_max = out_max
        self.out_range = out_max - out_min
        self.scale_values = scale_values

    def fit(self, x, y=None):
        """
        Calculate the values for the min/max transformation.
        """
        variables = np.arange(x.shape[1])
        self.scale_values = pd.DataFrame(0, index=variables, columns=["min", "max"])
        for v in variables:
            self.scale_values.loc[v, "min"] = x[:, v].min()
            self.scale_values.loc[v, "max"] = x[:, v].max()
            self.scale_values.loc[v, "range"] = self.scale_values.loc[v, "max"] - self.scale_values.loc[v, "min"]

    def transform(self, x):
        """
        Apply the min/max scaling transformation.
        """
        if x.shape[1] != self.scale_values.index.size:
            raise ValueError("Input x does not have the correct number of variables")
        x_new = np.zeros(x.shape, dtype=x.dtype)
        for v in self.scale_values.index:
            x_new[:, v] = (x[:, v] - self.scale_values.loc[v, "min"]) \
                / (self.scale_values.loc[v, "range"])
            if self.out_min != 0 or self.out_max != 1:
                x_new[:, v] = x_new[:, v] * self.out_range + self.out_min
        return x_new

    def fit_transform(self, x, y=None):
        self.fit(x, y)
        return self.transform(x)
