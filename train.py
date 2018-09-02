import os
import torch
import numpy as np
from torch.autograd import Variable
from collections import defaultdict
from tensorboardX import SummaryWriter
from tqdm import tqdm

from data import initialize_loaders
from main import setup_main, to_variables, ModelSaver, update_stats
import models


def run_audio(opt):
    # Initialize DataLoaders
    train_loader, test_loader = initialize_loaders(opt, type=1)

    # Initialize Network
    net = load_or_init_models(models.crNN_audio(1, 10, 2), opt).cuda()

    # Optimizers
    optimizer = torch.optim.Adam(net.parameters(), lr=opt.lr, betas=(opt.b1, opt.b2))
    # optimizer = torch.optim.SGD(net.parameters(), lr=0.0002)
    criterion = torch.nn.BCELoss()
    net_saver = ModelSaver(f'{opt.checkpoint_dir}/saved_models/{opt.name}')

    train_writer = SummaryWriter(log_dir=os.path.join(opt.checkpoint_dir, 'train'))
    test_writer = SummaryWriter(log_dir=os.path.join(opt.checkpoint_dir, 'test'))

    for epoch in tqdm(range(opt.epoch, opt.n_epochs), desc='Training'):
        # Training
        avg_stats = defaultdict(float)
        for i, data in enumerate(train_loader):
            loss, output = train_audio(net, criterion, optimizer, data, opt)
            update_stats(avg_stats, loss)

        # Log training progress
        str_out = '[train] {}/{} '.format(epoch, opt.n_epochs)
        for k, v in avg_stats.items():
            avg = v / len(train_loader)
            train_writer.add_scalar(k, avg, epoch)
            str_out += '{}: {:.6f}  '.format(k, avg)
        print(str_out)

        # Testing
        avg_stats = defaultdict(float)
        with torch.no_grad():
            for i, data in enumerate(test_loader):
                loss, output = test_audio(net, criterion, data, opt)
                update_stats(avg_stats, loss)

        # Log testing progress
        str_out = '[test] {}/{} '.format(epoch, opt.n_epochs)
        avg = 0
        for k, v in avg_stats.items():
            avg = v / len(test_loader)
            test_writer.add_scalar(k, avg, epoch)
            str_out += '{}: {:.6f}  '.format(k, avg)
        print(str_out)

        if epoch % opt.checkpoint_interval == 0:
            # Save model checkpoints
            net_saver.save_if_best(net, avg)

def train_audio(net, criterion, optimizer, data, opt):
    net.train()
    optimizer.zero_grad()

    volumes, labels, lengths = data
    if opt.cuda:
        volumes = volumes.cuda()
        labels = labels.cuda()

    output = net(volumes*100, lengths)
    losses = criterion(output, labels)
    losses.backward()
    optimizer.step()

    return {'train loss': losses.sum(), 'accuracy': (labels == output.round()).cpu().numpy().astype(bool).all(1).mean()}, output

def test_audio(net, criterion, data, opt):
    net.eval()

    volumes, labels, lengths = data
    if opt.cuda:
        volumes = volumes.cuda()
        labels = labels.cuda()

    output = net(volumes, lengths)
    losses = criterion(output, labels)

    return {'test loss': losses.sum(), 'accuracy': (labels == output.round()).cpu().numpy().astype(bool).all(1).mean()}, output

def run(opt):
    # Initialize DataLoaders
    train_loader, test_loader = initialize_loaders(opt)

    # Initialize Network
    net = load_or_init_models(models.crNN(130, 10, 1), opt).cuda()

    # Optimizers
    optimizer = torch.optim.Adam(net.parameters(), lr=opt.lr, betas=(opt.b1, opt.b2))
    criterion = torch.nn.CrossEntropyLoss()
    net_saver = ModelSaver(f'{opt.checkpoint_dir}/saved_models/{opt.name}')

    train_writer = SummaryWriter(log_dir=os.path.join(opt.checkpoint_dir, 'train'))
    test_writer = SummaryWriter(log_dir=os.path.join(opt.checkpoint_dir, 'test'))

    for epoch in tqdm(range(opt.epoch, opt.n_epochs), desc='Training'):
        # Training
        avg_stats = defaultdict(float)
        for i, data in enumerate(train_loader):
            data = to_variables(data, cuda=opt.cuda, device=opt.device)
            loss = train(net, criterion, optimizer, data, opt)
            update_stats(avg_stats, loss)

        # Log training progress
        str_out = '[train] {}/{} '.format(epoch, opt.n_epochs)
        for k, v in avg_stats.items():
            avg = v / len(train_loader)
            train_writer.add_scalar(k, avg, epoch)
            str_out += '{}: {:.6f}  '.format(k, avg)
        print(str_out)

        # Testing
        avg_stats = defaultdict(float)
        with torch.no_grad():
            for i, data in enumerate(test_loader):
                data = to_variables(data, cuda=opt.cuda, device=opt.device, test=True)
                losses = test(net, criterion, data, opt)
                update_stats(avg_stats, losses)

        # Log testing progress
        str_out = '[test] {}/{} '.format(epoch, opt.n_epochs)
        avg = 0
        for k, v in avg_stats.items():
            avg = v / len(test_loader)
            test_writer.add_scalar(k, avg, epoch)
            str_out += '{}: {:.6f}  '.format(k, avg)
        print(str_out)

        if epoch % opt.checkpoint_interval == 0:
            # Save model checkpoints
            net_saver.save_if_best(net, avg)

def train(net, criterion, optimizer, data, opt):
    net.train()
    optimizer.zero_grad()

    frames, volumes, labels = data
    output = Variable(net(frames[0], volumes[0]), requires_grad=True)
    losses = criterion(output, labels)
    losses.backward()
    optimizer.step()

    return {'train loss': losses.mean()}

def test(net, criterion, data, opt, lambda_pixel=100):
    net.eval()

    frames, volumes, labels = data
    frame = frames[0]
    audio = volumes[0]
    output = net(frame, audio)
    losses = criterion(output, labels)

    return {'test loss': losses.mean()}

def benchmark(opt):
    train_loader, test_loader = initialize_loaders(opt)

    # Initialize net
    net = load_or_init_models(models.crNN(130, 10, 1), opt).cuda()

    output = np.zeros(len(test_loader) + len(train_loader))
    label_glob = np.zeros(len(test_loader) + len(train_loader))
    idx = 0
    with torch.no_grad():
        for i, data in enumerate(train_loader):
            data = to_variables(data, cuda=opt.cuda, device=opt.device, test=True)
            frames, volumes, labels = data
            frame = frames[0]
            audio = volumes[0]
            output[idx] = net(frame, audio)
            label_glob[idx] = labels[0]
            idx = idx + 1


        for i, data in enumerate(test_loader):
            data = to_variables(data, cuda=opt.cuda, device=opt.device, test=True)
            frames, volumes, labels = data
            frame = frames[0]
            audio = volumes[0]
            output[idx] = net(frame, audio)
            label_glob[idx] = labels[0]
            idx = idx + 1

    final_tag = np.round(output)

    return final_tag

def load_or_init_models(model, opt):
    if opt.net != '':
        model.load_state_dict(torch.load(opt.net))
    if opt.cuda:
        model = model.cuda()
    return model

if __name__ == '__main__':
    opt = setup_main()
    if opt.benchmark:
        benchmark(opt)
    else:
        run_audio(opt)
