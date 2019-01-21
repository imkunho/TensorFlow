import tensorflow as tf
import numpy as np
from tensorflow.keras.utils import to_categorical
from tensorflow.keras.datasets import mnist
from time import time
import os

tf.enable_eager_execution()


def load(model, checkpoint_dir):
    print(" [*] Reading checkpoints...")

    ckpt = tf.train.get_checkpoint_state(checkpoint_dir)
    if ckpt:
        ckpt_name = os.path.basename(ckpt.model_checkpoint_path)
        checkpoint = tf.train.Checkpoint(dnn=model)
        checkpoint.restore(save_path=os.path.join(checkpoint_dir, ckpt_name))
        counter = int(ckpt_name.split('-')[1])
        print(" [*] Success to read {}".format(ckpt_name))
        return True, counter
    else:
        print(" [*] Failed to find a checkpoint")
        return False, 0


def normalize(X_train, X_test):
    X_train = X_train / 255.0
    X_test = X_test / 255.0

    return X_train, X_test


def load_mnist():
    (train_data, train_labels), (test_data, test_labels) = mnist.load_data()
    train_data = np.expand_dims(train_data, axis=-1)  # [N, 28, 28] -> [N, 28, 28, 1]
    test_data = np.expand_dims(test_data, axis=-1)  # [N, 28, 28] -> [N, 28, 28, 1]

    train_data, test_data = normalize(train_data, test_data)

    train_labels = to_categorical(train_labels, 10)  # [N,] -> [N, 10]
    test_labels = to_categorical(test_labels, 10)  # [N,] -> [N, 10]

    return train_data, train_labels, test_data, test_labels


def loss_fn(model, x, label, training=True):
    logit = model(x, training=training)
    loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits_v2(labels=label, logits=logit))
    accuracy = accuracy_fn(logit, label)

    return loss, accuracy


def accuracy_fn(logit, label):
    prediction = tf.equal(tf.argmax(logit, -1), tf.argmax(label, -1))
    accuracy = tf.reduce_mean(tf.cast(prediction, tf.float32))
    return accuracy


class Network_class(tf.keras.Model):
    def __init__(self, label_dim):
        super(Network_class, self).__init__()
        weight_init = tf.keras.initializers.glorot_uniform()

        self.dense_layers = []
        self.batch_norm_layers = []
        self.flatten = tf.keras.layers.Flatten() # [N, 28, 28, 1] -> [N, 784]
        self.relu = tf.keras.activations.relu

        for i in range(4):
            # [N, 784] -> [N, 512] -> [N, 512] -> [N, 512] -> [N, 512]
            self.dense_layers.append(tf.keras.layers.Dense(units=512, use_bias=True, kernel_initializer=weight_init))
            self.batch_norm_layers.append(tf.keras.layers.BatchNormalization())

        # [N, 512] -> [N, 10]
        self.logit = tf.keras.layers.Dense(units=label_dim, use_bias=True, kernel_initializer=weight_init)

    def call(self, x, training=True, mask=None):
        x = self.flatten(x)

        for dense, batch_norm in zip(self.dense_layers, self.batch_norm_layers) :
            x = dense(x)
            x = batch_norm(x, training=training)
            x = self.relu(x)

        x = self.logit(x)

        return x


""" dataset """
train_x, train_y, test_x, test_y = load_mnist()

""" parameters """
learning_rate = 0.001
batch_size = 128

training_epochs = 1
training_iterations = len(train_x) // batch_size

img_size = 28
c_dim = 1
label_dim = 10

train_flag = True

""" Graph Input using Dataset API """
train_dataset = tf.data.Dataset.from_tensor_slices((train_x, train_y)). \
    shuffle(buffer_size=100000). \
    prefetch(buffer_size=batch_size). \
    batch(batch_size). \
    repeat()

test_dataset = tf.data.Dataset.from_tensor_slices((test_x, test_y)). \
    shuffle(buffer_size=100000). \
    prefetch(buffer_size=len(test_x)). \
    batch(len(test_x)). \
    repeat()

train_iterator = train_dataset.make_one_shot_iterator()
test_iterator = test_dataset.make_one_shot_iterator()


""" Model """
network = Network_class(label_dim)

""" Training """
optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)

""" Writer """
checkpoint_dir = 'checkpoints'
logs_dir = 'logs'

model_dir = 'nn_batchnorm'

checkpoint_prefix = os.path.join(checkpoint_dir, model_dir)
logs_dir = os.path.join(logs_dir, model_dir)

if train_flag:

    checkpoint = tf.train.Checkpoint(dnn=network)

    # create writer for tensorboard
    summary_writer = tf.contrib.summary.create_file_writer(logdir=logs_dir)
    start_time = time()

    # restore check-point if it exits
    could_load, checkpoint_counter = load(network, checkpoint_dir)
    global_step = tf.train.create_global_step()

    if could_load:
        start_epoch = (int)(checkpoint_counter / training_iterations)
        start_iteration = checkpoint_counter - start_epoch * training_iterations
        counter = checkpoint_counter
        global_step.assign(checkpoint_counter)
        print(" [*] Load SUCCESS")
    else:
        start_epoch = 0
        start_iteration = 0
        counter = 0
        print(" [!] Load failed...")

    with summary_writer.as_default(), tf.contrib.summary.always_record_summaries():  # for tensorboard
        for epoch in range(start_epoch, training_epochs):
            for idx in range(start_iteration, training_iterations):
                train_input, train_label = train_iterator.get_next()

                with tf.GradientTape() as tape:
                    train_loss, train_accuracy = loss_fn(network, train_input, train_label)

                test_input, test_label = test_iterator.get_next()
                _, test_accuracy = loss_fn(network, test_input, test_label, training=False)

                grads = tape.gradient(target=train_loss, sources=network.variables)
                optimizer.apply_gradients(grads_and_vars=zip(grads, network.variables), global_step=global_step)

                tf.contrib.summary.scalar(name='train_loss', tensor=train_loss)
                tf.contrib.summary.scalar(name='train_accuracy', tensor=train_accuracy)
                tf.contrib.summary.scalar(name='test_accuracy', tensor=test_accuracy)

                print("Epoch: [%2d] [%5d/%5d] time: %4.4f, train_loss: %.8f, train_accuracy: %.2f, test_Accuracy: %.2f" \
                      % (epoch, idx, training_iterations, time() - start_time, train_loss, train_accuracy,
                         test_accuracy))
                counter += 1
        checkpoint.save(file_prefix=checkpoint_prefix + '-{}'.format(counter))

else:
    _, _ = load(network, checkpoint_dir)
    test_input, test_label = test_iterator.get_next()
    _, test_accuracy = loss_fn(network, test_input, test_label)

    print("test_Accuracy: %.2f" % (test_accuracy))