#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Project      : Project
# @Author       : Xiaoyu LIN
# @File         : DataPreprocessing.py
# @Description  :
import argparse
import os
from datetime import datetime
from data.util import *


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def read_data(dataset_path):
    """
    Load data from raw dataset.
    :param dataset_path: the full name of dataset including extension name
    :return sess_map: map from raw data session name to session Id, a dictionary sess_map[sess_name]=sessId
    :return item_map: map from raw data item name to item Id, a dictionary item_map[item_name]=itemId
    :return reformed_data: a list: each element is a action, which is a list of [sessId, itemId, time]
    """
    # load data according to file extension name
    filename_extension = dataset_path.split('/')[-1].split('.')[-1]
    if filename_extension == 'gz':
        sess_map, item_map, reformed_data = read_gz(dataset_path)
    elif filename_extension == 'dat':
        sess_map, item_map, reformed_data = read_dat(dataset_path)
    elif filename_extension == 'csv':
        sess_map, item_map, reformed_data = read_csv(dataset_path)
    else:
        print("Error: new data file type !!!")

    # print raw dataset information
    print('Total number of sessions in dataset:', len(sess_map.keys()))
    print('Total number of items in dataset:', len(item_map.keys()))
    print('Total number of actions in dataset:', len(reformed_data))
    print('Average number of actions per user:', len(reformed_data) / len(sess_map.keys()))
    print('Average number of actions per item:', len(reformed_data) / len(item_map.keys()))

    return sess_map, item_map, reformed_data


def short_remove(reformed_data, args):
    """
    Remove data according to threshold
    :param reformed_data: loaded data, a list: each element is a action, which is a list of [sessId, itemId, time]
    :param args.threshold_item: minimum number of appearance time of item -1
    :param args.threshold_sess: minimum length of session -1
    :return removed_data: result data after removing
    :return sess_end: a map recording session end time, a dictionary sess_end[sessId]=end_time
    """
    # if args.yoochoose_select and not args.is_time_fraction and args.dataset == 'yoochoose-clicks.dat':
    #     max_time = max(map(lambda x: x[2], reformed_data))
    #     if args.test_fraction == 'day':
    #         test_threshold = max_time - 86400
    #     elif args.test_fraction == 'week':
    #         test_threshold = max_time - 86400 * 7
    #     valid_time = list(map(lambda x: x[2], reformed_data))
    #     valid_time = list(filter(lambda x: x < test_threshold, valid_time))
    #     threshold = np.percentile(valid_time, (1 - args.yoochoose_select) * 100)
    #     reformed_data = list(filter(lambda x: x[2] > threshold, reformed_data))

    # remove session whose length is 1
    sess_counter = defaultdict(lambda: 0)
    for [userId, _, _] in reformed_data:
        sess_counter[userId] += 1
    removed_data = list(filter(lambda x: sess_counter[x[0]] > 1, reformed_data))

    # remove item which appear less or equal to threshold_item
    item_counter = defaultdict(lambda: 0)
    for [_, itemId, _] in removed_data:
        item_counter[itemId] += 1
    removed_data = list(filter(lambda x: item_counter[x[1]] > args.threshold_item, removed_data))

    # remove session whose length less or equal to threshold_sess
    sess_counter = defaultdict(lambda: 0)
    for [userId, _, _] in removed_data:
        sess_counter[userId] += 1
    removed_data = list(filter(lambda x: sess_counter[x[0]] > args.threshold_sess, removed_data))

    # record session end time
    sess_end = dict()
    for [userId, _, time] in removed_data:
        sess_end = generate_sess_end_map(sess_end, userId, time)



    # print information of removed data
    print('Number of sessions after pre-processing:', len(set(map(lambda x: x[0], removed_data))))
    print('Number of items after pre-processing:', len(set(map(lambda x: x[1], removed_data))))
    print('Number of actions after pre-processing:', len(removed_data))
    print('Average number of actions per session:', len(removed_data) / len(set(map(lambda x: x[0], removed_data))))
    print('Average number of actions per item:', len(removed_data) / len(set(map(lambda x: x[1], removed_data))))

    return removed_data, sess_end


def time_partition(removed_data, session_end, args):
    """
    Partition data according to time periods
    :param removed_data: input data, a list: each element is a action, which is a list of [sessId, itemId, time]
    :param session_end: a dictionary recording session end time, session_end[sessId]=end_time
    :param args.time_fraction: time interval for partition
    :param args.is_time_fraction: boolean, weather partition or not
    :return: time_fraction: a dictionary, the keys are different time periods,
    value is a list of actions in that time period
    """
    if args.is_time_fraction:
        time_fraction = dict()
        all_times = np.array(list(session_end.values()))
        max_time = max(all_times)
        min_time = min(all_times)
        period_threshold = np.arange(max_time, min_time, -7 * 86400)
        period_threshold = np.sort(period_threshold)
        if args.dataset.split('.')[0] == 'train-item-views':
            period_threshold = period_threshold[4:]

        for [sessId, itemId, time] in removed_data:
            # find period of each action
            period = period_threshold.searchsorted(time) + 1
            # generate time period for dictionary keys
            if period not in time_fraction:
                time_fraction[period] = []
            # partition data according to period
            time_fraction[period].append([sessId, itemId, time])
    else:
        # if not partition, put all actions in the last period
        time_fraction = removed_data

    return time_fraction


def generating_txt(time_fraction, sess_end, args):
    """
    Generate final txt file
    :param time_fraction: input data, a dictionary, the keys are different time periods,
    value is a list of actions in that time period
    :param sess_end: session end time map, sess_map[sessId]=end_time
    """

    if args.is_time_fraction:
        # item map second time
        item_map = {}
        for period in sorted(time_fraction.keys()):
            time_fraction[period].sort(key=lambda x: x[2])
        for period in sorted(time_fraction.keys()):
            for i, [userId, itemId, time] in enumerate(time_fraction[period]):
                itemId = generate_name_Id_map(itemId, item_map)
                time_fraction[period][i] = [userId, itemId, time]

        # sort action according to time sequence
        for period in sorted(time_fraction.keys()):
            time_fraction[period].sort(key=lambda x: x[2])

        for i, period in enumerate(sorted(time_fraction.keys()), start=1):
            with open('week_' + str(i) + '.txt', 'w') as file_train:
                for [userId, itemId, time] in time_fraction[period]:
                    file_train.write('%d %d\n' % (userId, itemId))
    else:
        # item map second time
        item_map = {}
        time_fraction.sort(key=lambda x: x[2])
        for i, [userId, itemId, time] in enumerate(time_fraction):
            itemId = generate_name_Id_map(itemId, item_map)
            time_fraction[i] = [userId, itemId, time]

        # sort action according to time sequence
        time_fraction.sort(key=lambda x: x[2])

        max_time = max(map(lambda x: x[2], time_fraction))
        if args.test_fraction == 'day':
            test_threshold = 86400
        elif args.test_fraction == 'week':
            test_threshold = 86400 * 7

        with open('test.txt', 'w') as file_test, open('train.txt', 'w') as file_train:
            for [userId, itemId, time] in time_fraction:
                if sess_end[userId] < max_time - test_threshold:
                    file_train.write('%d %d\n' % (userId, itemId))
                else:
                    file_test.write('%d %d\n' % (userId, itemId))


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default='train-item-views.csv', type=str)
    parser.add_argument('--is_time_fraction', default=False, type=str2bool)
    parser.add_argument('--test_fraction', default='week', type=str)
    parser.add_argument('--threshold_sess', default=1, type=int)
    parser.add_argument('--threshold_item', default=4, type=int)
    parser.add_argument('--yoochoose_select', default=0.25, type=float)
    args = parser.parse_args()
    # args.dataset = 'yoochoose-clicks.dat'
    print('Start preprocess ' + args.dataset + ':')

    # For reproducibility
    SEED = 666
    np.random.seed(SEED)

    # load data and get the session and item lookup table
    os.chdir('dataset')
    sess_map, item_map, reformed_data = read_data(args.dataset)

    # create dictionary for processed data
    if args.dataset.split('.')[0] == 'yoochoose-clicks':
        dataset_name = 'YOOCHOOSE'
    elif args.dataset.split('.')[0] == 'train-item-views':
        dataset_name = 'DIGINETICA'
    if args.is_time_fraction:
        dataset_name = dataset_name
    else:
        dataset_name = dataset_name + '_joint'
    if not os.path.isdir(os.path.join('..', dataset_name)):
        os.makedirs(os.path.join('..', dataset_name))
    os.chdir(os.path.join('..', dataset_name))

    # remove data according to occurrences time
    removed_data, sess_end = short_remove(reformed_data, args)

    # partition data according to time periods
    time_fraction = time_partition(removed_data, sess_end, args)

    # generate final txt file
    generating_txt(time_fraction, sess_end, args)

    if args.is_time_fraction:
        plot_stat(time_fraction)

    print(args.dataset + ' finish!')
