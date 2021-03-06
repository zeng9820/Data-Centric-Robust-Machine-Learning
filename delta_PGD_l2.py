# Modified version based on https://github.com/ZhengyuZhao/Targeted-Tansfer/blob/main/eval_ensemble.py

import torch
import torch.nn as nn
from torchvision import transforms
from models import resnet50
from PIL import Image
from tqdm import tqdm
import numpy as np

device = torch.device("cuda:0")


# simple Module to normalize an image
class Normalize(nn.Module):
    def __init__(self, mean, std):
        super(Normalize, self).__init__()
        self.mean = torch.Tensor(mean)
        self.std = torch.Tensor(std)

    def forward(self, x):
        return (x - self.mean.type_as(x)[None, :, None, None]) / self.std.type_as(x)[None, :, None, None]


model = resnet50()
checkpoint = torch.load('./models/trained/resnet50.pth.tar')
model.load_state_dict(checkpoint['state_dict'])
model.eval()

for param in model.parameters():
    param.requires_grad = False

model.to(device)

torch.manual_seed(42)
torch.backends.cudnn.deterministic = True

# values are standard normalization for CIFAR-10 images
norm = Normalize(mean=[0.4914, 0.4822, 0.4465], std=[0.2023, 0.1994, 0.2010])
trn = transforms.Compose([transforms.ToTensor(), ])
images = np.load('./cifar10/test_data.npy')
labels = np.load('./cifar10/test_label.npy')
labels = np.argmax(labels, axis=1)

batch_size = 16
max_iterations = 300
num_batches = np.int32(np.ceil(len(images) / batch_size))
img_size = 32
lr = 0.025
epsilon = 1.0

adv_img = np.zeros_like(images)
for k in tqdm(range(0, num_batches)):
    batch_size_cur = min(batch_size, len(images) - k * batch_size)
    X_ori = torch.zeros(batch_size_cur, 3, img_size, img_size).to(device)
    delta = torch.zeros_like(X_ori, requires_grad=True).to(device)
    for i in range(batch_size_cur):
        X_ori[i] = trn(Image.fromarray(images[k * batch_size + i]))
    label = torch.LongTensor(labels[k * batch_size:k * batch_size + batch_size_cur]).to(device)
    prev = float('inf')
    for t in tqdm(range(max_iterations)):
        logit = model(norm(X_ori + delta))
        loss = nn.CrossEntropyLoss()(logit, label)
        loss.backward()
        grad = delta.grad.clone()
        delta.grad.zero_()
        for j in range(batch_size_cur):
            delta.data[j] = delta.data[j] + lr * grad[j] / torch.linalg.norm(grad[j])
            delta.data[j] = delta.data[j] / max(1., torch.linalg.norm(delta.data[j]))
            delta.data[j] = ((X_ori[j] + delta.data[j]).clamp(0, 1)) - X_ori[j]
    for j in range(batch_size_cur):
        x_np = transforms.ToPILImage()((X_ori + delta)[j].detach().cpu())
        adv_img[k * batch_size + j] = x_np

np.save('delta_pgd_l2.npy', adv_img.astype(np.int32) - images.astype(np.int32))
torch.cuda.empty_cache()
