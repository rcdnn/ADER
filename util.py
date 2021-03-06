#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Project      : ADER
# @File         : util.py
# @Author       : Xiaoyu Lin

from typing import Any, Callable, List, Optional, Union, Tuple, TextIO, Set
import random
import os
import numpy as np
import math
from collections import defaultdict
from tqdm import tqdm


class DataLoader:
    """ DataLoader object to load train, valid and test data from dataset.
    Args:
        dataset (str): Name of the dataset.
    """

    def __init__(self,
                 dataset: str,
                 ) -> None:

        self.item_set = set()
        self.path = os.path.join('..', '..', 'data', dataset)
        # remove item in testing data that not appeared in training data
        self.is_remove_item = True

    def train_loader(self,
                     period: int
                     ) -> (list, str):
        """ This method load train data of specific period.
        Args:
            period (int): The period which load training data from.
        Returns:
            sessions (list): Training item sequences (session) of selected periods.
            info (str): Information of training data.
        """
        Sessions = defaultdict(list)
        file_name = '/period_%d.txt' % period
        with open(self.path + file_name, 'r') as f:
            for line in f:
                sessId, itemId = line.rstrip().split(' ')
                sessId = int(sessId)
                itemId = int(itemId)
                self.item_set.add(itemId)
                Sessions[sessId].append(itemId)

        sessions = list(Sessions.values())
        del Sessions
        info = 'Train set information: total number of action: %d.' \
               % sum(list(map(lambda session: len(session), sessions)))
        print(info)

        return sessions, info

    def evaluate_loader(self,
                        period: int,
                        ) -> (list, str):
        """ This method loads test data of specific period.
        Args:
            period (int): The period which load testing data from.
        Returns:
            sessions (list): Testing item sequences (session) of selected periods.
            info (str): Information of testing data.
        """
        Sessions = defaultdict(list)
        removed_num = 0
        total_num = 0
        file_name = '/period_%d.txt' % period
        with open(self.path + file_name, 'r') as f:
            for line in f:
                total_num += 1
                sessId, itemId = line.rstrip().split(' ')
                sessId = int(sessId)
                itemId = int(itemId)
                # remove new items in test or validation set that not appear in train set
                if self.is_remove_item and (itemId not in self.item_set):
                    removed_num += 1
                    continue
                else:
                    self.item_set.add(itemId)
                Sessions[sessId].append(itemId)

        if self.is_remove_item:
            delete_keys = []
            for sessId in Sessions:
                if len(Sessions[sessId]) == 1:
                    removed_num += 1
                    delete_keys.append(sessId)
            for delete_key in delete_keys:
                del Sessions[delete_key]

        info = 'Test set information: original total number of action: %d, removed number of action: %d.' \
               % (total_num, removed_num)
        sessions = list(Sessions.values())
        del Sessions

        return sessions, info

    def max_item(self) -> int:
        """ This method returns the maximum item number in current cycle training data.
        """
        return max(self.item_set)


class Sampler:
    """ This object samples data and generates positive labels for train, valid and test data,
            as well as negative sample for training data.
    Args:
        data (list): Original data needs to be sampled.
        maxlen (int): The length of each sequence.
        batch_size (int): The number of data in one batch.
        is_subseq (bool): If True, the given data is sub-sequence. If False, the given data is full
            original data.
    """

    def __init__(self,
                 data: list,
                 maxlen: int,
                 batch_size: int,
                 is_subseq: bool = False
                 ) -> None:

        self.maxlen = maxlen
        self.batch_size = batch_size

        self.dataset_size = 0
        self.batch_counter = 0
        self.data_indices = []

        self.prepared_data = []
        if not is_subseq:
            for session in data:
                self.prepared_data.append(session)
                length = len(session)
                if length > 2:
                    for t in range(1, length - 1):
                        self.prepared_data.append(session[:-t])
        else:
            for session in data:
                self.prepared_data.append(session)

        self.data_indices = list(range(len(self.prepared_data)))
        random.shuffle(self.data_indices)

    def label_generator(self,
                        session: list,
                        ) -> (list, int):
        """ This method split sessions into input sequence and labels.
        Args:
            session (list): Original sub-sequence of different length.
        Return:
            seq (list): The input sequence with fixed length set by maxlen.
            pos (int): Label (item number).
        """
        seq = np.zeros([self.maxlen], dtype=np.int32)
        pos = np.array(session[-1], dtype=np.int32)
        idx = self.maxlen - 1

        for itemId in reversed(session[:-1]):
            seq[idx] = itemId
            idx -= 1
            if idx == -1:
                break

        return seq, pos

    def add_exemplar(self,
                     exemplar: list
                     ) -> None:
        """ Add exemplar data and logits from previous cycle model
        Args:
             exemplar (list): Exemplar data and corresponding logits.
        """
        self.logits = []
        for session, logits in exemplar:
            self.prepared_data.append(session)
            self.logits.append(logits)

        self.data_indices = list(range(len(self.prepared_data)))
        random.shuffle(self.data_indices)

    def split_data(self,
                   valid_portion: float,
                   return_train: bool = False
                   ) -> Union[list, tuple]:
        """ Split data into valid and train dataset and remove validation data from original training data.
        Args:
            valid_portion (float): The portion of validation dataset w.r.t entire dataset.
            return_train: If True, return validation data and train data, else only return validation data.
        Returns:
            valid_data (list): Validation sub-sequence.
            train_data (list): Training sub-sequence.
        """

        data_size = len(self.prepared_data)
        sidx = np.arange(data_size, dtype='int32')
        np.random.shuffle(sidx)

        n_train = int(np.round(data_size * (1. - valid_portion)))
        valid_data = [self.prepared_data[s] for s in sidx[n_train:]]
        train_data = [self.prepared_data[s] for s in sidx[:n_train]]
        self.prepared_data = train_data

        self.data_indices = list(range(len(self.prepared_data)))
        random.shuffle(self.data_indices)

        if return_train:
            return valid_data, train_data
        else:
            return valid_data

    def sampler(self) -> list:
        """ This method returns a batch of sample: N * (sequence, label).
        Returns:
            one_batch (list): One batch of data in the size of N * (sequence length, 1).
        """
        one_batch = []
        for i in range(self.batch_size):
            if (i + self.batch_counter * self.batch_size) < len(self.prepared_data):
                index = self.data_indices[i + self.batch_counter * self.batch_size]
                session = self.prepared_data[index]
                if len(session) <= 1:
                    continue
                one_batch.append(self.label_generator(session))
            else:
                break

        self.batch_counter += 1
        if self.batch_counter == self.batch_num():
            self.batch_counter = 0
            random.shuffle(self.data_indices)

        return zip(*one_batch)

    def exemplar_sampler(self) -> list:
        """ This method returns a batch of exemplar data: N * (exemplar, logits).
        Return:
            one_batch (list): One batch of data in the size of N * (sequence length, previous item number).
        """
        one_batch = []
        for i in range(self.batch_size):
            if (i + self.batch_counter * self.batch_size) < len(self.prepared_data):
                index = self.data_indices[i + self.batch_counter * self.batch_size]
                session = self.prepared_data[index]
                if len(session) <= 1:
                    continue
                seq, pos = self.label_generator(session)
                one_batch.append((seq, pos, self.logits[index]))
            else:
                break

        self.batch_counter += 1
        if self.batch_counter == self.batch_num():
            self.batch_counter = 0
            random.shuffle(self.data_indices)

        return zip(*one_batch)

    def data_size(self) -> int:
        """ Get the number of sub-sequences in the data set.
        Returns:
            (int): The number of sub-sequences in the data set.
        """
        return len(self.prepared_data)

    def batch_num(self) -> int:
        """ Get the number of batches according to dataset size and batch size.
        Return:
            (int): The number of batches in one epoch.
        """
        return math.ceil(len(self.prepared_data) * 1.0 / self.batch_size)


class Evaluator:
    """ This object evaluates performance on valid or test data.
    """

    def __init__(self, data, is_subseq, maxlen, batch_size, max_item, mode, model, sess, logs):
        """
        :param args: args
        :param data: data to evaluate, valid data or test data
        :param max_item: maximum item at current period
        :param model: model
        :param mode: 'valid' or 'test'
        :param sess: tf session
        :param logs: logs
        """
        self.maxlen = maxlen
        self.batch_size = batch_size
        self.data = data
        self.max_item = max_item
        self.mode = mode
        self.model = model
        self.sess = sess

        self.logs = logs
        self.ranks = []
        self.recall_20 = 0
        self.desc = 'Validating epoch ' if mode == 'valid' else 'Testing epoch '
        self.evaluate_sampler = Sampler(data, maxlen, batch_size, is_subseq=is_subseq)

    def evaluate(self, epoch):
        """
        This method only evaluate performance of predicted last item among all existing item.
        :param exemplar: valid exemplar from previous period
        :param epoch: current epoch
        """
        self.ranks = []
        batch_num = self.evaluate_sampler.batch_num()
        for _ in tqdm(range(batch_num), total=batch_num, ncols=70, leave=False, unit='b',
                      desc=self.desc + str(epoch)):
            seq, pos = self.evaluate_sampler.sampler()
            predictions = self.model.predict(self.sess, seq, list(range(1, self.max_item + 1)))
            ground_truth = pos
            rank = [pred[index - 1] for pred, index in zip(predictions, ground_truth)]
            self.ranks.extend(rank)
        self.display(epoch)

    def results(self):
        """ This method returns evaluation results (MRR@20, RECALL@20, MRR@10, RECALL@10)
        """
        valid_user = len(self.ranks)
        valid_ranks_20 = list(filter(lambda x: x < 20, self.ranks))
        valid_ranks_10 = list(filter(lambda x: x < 10, self.ranks))
        RECALL_20 = len(valid_ranks_20)
        MRR_20 = sum(map(lambda x: 1.0 / (x + 1), valid_ranks_20))
        RECALL_10 = len(valid_ranks_10)
        MRR_10 = sum(map(lambda x: 1.0 / (x + 1), valid_ranks_10))
        return MRR_20 / valid_user, RECALL_20 / valid_user, MRR_10 / valid_user, RECALL_10 / valid_user

    def display(self, epoch):
        """
        This method display and save evaluation metrics(MRR@20, RECALL@20, MRR@10, RECALL@10)
        """
        results = self.results()
        info = 'epoch:%d, %s (MRR@20: %.4f, RECALL@20: %.4f, MRR@10: %.4f, RECALL@10: %.4f)' \
               % (epoch, self.mode, results[0], results[1], results[2], results[3])
        print(info)
        self.logs.write(info + '\n')


class ExemplarGenerator:
    """ This object select exemplars from given data.
    Args:
        data (List): train data, valid data at current cycle and exemplar data from previous cycle in the
            from of sub-sequence.

    """

    def __init__(self, data, exemplar_size, disable_m, batch_size, maxlen, dropout_rate, max_item, logs):
        """
        :param m: number of exemplars per item
        :param data: train data, valid data at current cycle and exemplar data from previous cycle
        :param max_item: accumulative number of item
        :param logs: logs
        """
        self.exemplars = dict()
        self.m = exemplar_size
        self.data = data
        self.max_item = max_item
        self.logs = logs
        self.item_count = np.zeros(max_item)
        self.dropout_rate = dropout_rate

        self.sess_by_item = defaultdict(list)
        exemplar_sampler = Sampler(data, maxlen, batch_size, is_subseq=True)
        batch_num = exemplar_sampler.batch_num()

        for _ in tqdm(range(batch_num), total=batch_num, ncols=70, leave=False, unit='b',
                      desc='Sorting exemplars'):
            seq, pos = exemplar_sampler.sampler()
            pos = np.array(pos)
            for s, item in zip(seq, pos):
                session = np.append(s, item)
                self.sess_by_item[item].append(session)
                self.item_count[item - 1] += 1

        self.exemplars = defaultdict(list)
        if disable_m:
            self.item_count = np.ones_like(self.item_count)
        item_prob = self.item_count / self.item_count.sum()
        item_count = np.random.multinomial(n=self.m, pvals=item_prob, size=1)[0]
        self.item_count = np.int32(item_count)

    def herding(self, rep, logits, item, seq, m):
        """
        Herding algorithm for exemplar selection
        :param rep: representations
        :param logits: logits
        :param item: label
        :param seq: input session (item sequence)
        :param m: number of exemplar per label
        """
        # Initialize mean and selected ids
        D = rep.T / np.linalg.norm(rep.T, axis=0)
        mu = D.mean(axis=1)
        w_t = mu
        step_t = 0
        selected_ids = []
        counter = 0
        while not (len(selected_ids) == m) and step_t < 1.1 * m:
            tmp_t = np.dot(w_t, D)
            ind_max = np.argmax(tmp_t)
            w_t = w_t + mu - D[:, ind_max]
            step_t += 1
            if ind_max not in selected_ids:
                selected_ids.append(ind_max)
                counter += 1
        self.exemplars[item] = [[seq[i][seq[i] != 0].tolist(), logits[i].tolist()] for i in selected_ids]
        return counter

    def herding_selection(self, sess, model):
        """
        This method selects exemplars using herding and selects exemplars, the number of exemplars is proportional to
        item frequency.
        """
        saved_num = 0
        for item in tqdm(self.sess_by_item, ncols=70, leave=False, unit='b', desc='Selecting exemplar'):
            m = self.item_count[item - 1]
            seq = self.sess_by_item[item]
            seq = np.array(seq)
            input_seq = seq[:, :-1]
            rep, logits = sess.run([model.rep, model.logits], {model.input_seq: input_seq,
                                                               model.dropout_rate: self.dropout_rate,
                                                               model.max_item: self.max_item,
                                                               model.is_training: False})
            rep = np.array(rep)
            logits = np.array(logits)
            saved = self.herding(rep, logits, item, seq, min(m, len(seq)))
            saved_num += saved
        print('Total saved exemplar: %d' % saved_num)
        self.logs.write('Total saved exemplar: %d\n' % saved_num)

    def loss_selection(self, sess, model):
        """
        This method selects exemplars by ranking loss, the number of exemplars is proportional to
        item frequency.
        """
        saved_num = 0
        for item in tqdm(self.sess_by_item, ncols=70, leave=False, unit='b', desc='Selecting exemplar'):
            m = self.item_count[item - 1]
            if m < 0.5:
                continue
            seq = self.sess_by_item[item]
            seq_num = len(seq)
            seq = np.array(seq)
            loss, logits = sess.run([model.loss, model.logits], {model.input_seq: seq[:, :-1],
                                                                 model.pos: seq[:, -1],
                                                                 model.dropout_rate: self.dropout_rate,
                                                                 model.max_item: self.max_item,
                                                                 model.is_training: False})
            loss = np.array(loss)
            logits = np.array(logits)
            selected_ids = loss.argsort()[:int(min(m, seq_num))]
            self.exemplars[item] = [[seq[i][seq[i] != 0].tolist(), logits[i].tolist()] for i in selected_ids]
            saved_num += len(selected_ids)
        print('Total saved exemplar: %d' % saved_num)
        self.logs.write('Total saved exemplar: %d\n' % saved_num)

    def randomly_selection(self, sess, model):
        """
        This method randomly selects exemplars, and selects equivalent number of exemplar for each label.
        """
        saved_num = 0
        for item in tqdm(self.sess_by_item, ncols=70, leave=False, unit='b', desc='Selecting exemplar'):
            seq = self.sess_by_item[item]
            seq = np.array(seq)
            seq_num = len(seq)
            m = self.item_count[item - 1]
            if m > 0:
                selected_ids = np.random.choice(seq_num, min(m, seq_num), replace=False)
                selected_seq = seq[selected_ids]
                logits = sess.run(model.logits, {model.input_seq: selected_seq[:, :-1],
                                                 model.dropout_rate: self.dropout_rate,
                                                 model.max_item: self.max_item,
                                                 model.is_training: False})
                logits = np.array(logits)
                for s, l in zip(selected_seq, logits):
                    self.exemplars[item].append([s[s != 0].tolist(), l.tolist()])
                    saved_num += 1
        print('Total saved exemplar: %d' % saved_num)
        self.logs.write('Total saved exemplar: %d\n' % saved_num)
