# Ultralytics YOLO 🚀, AGPL-3.0 license

import os
import cv2
import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image


class FastSAMPrompt:

    def __init__(self, img_path, results, device='cuda') -> None:
        # self.img_path = img_path
        self.device = device
        self.results = results
        self.img_path = img_path
        self.ori_img = cv2.imread(img_path)

        # Import and assign clip
        try:
            import clip  # for linear_assignment
        except ImportError:
            from ultralytics.utils.checks import check_requirements
            check_requirements('git+https://github.com/openai/CLIP.git')  # required before installing lap from source
            import clip
        self.clip = clip

    @staticmethod
    def _segment_image(image, bbox):
        image_array = np.array(image)
        segmented_image_array = np.zeros_like(image_array)
        x1, y1, x2, y2 = bbox
        segmented_image_array[y1:y2, x1:x2] = image_array[y1:y2, x1:x2]
        segmented_image = Image.fromarray(segmented_image_array)
        black_image = Image.new('RGB', image.size, (255, 255, 255))
        # transparency_mask = np.zeros_like((), dtype=np.uint8)
        transparency_mask = np.zeros((image_array.shape[0], image_array.shape[1]), dtype=np.uint8)
        transparency_mask[y1:y2, x1:x2] = 255
        transparency_mask_image = Image.fromarray(transparency_mask, mode='L')
        black_image.paste(segmented_image, mask=transparency_mask_image)
        return black_image

    @staticmethod
    def _format_results(result, filter=0):
        annotations = []
        n = len(result.masks.data)
        for i in range(n):
            mask = result.masks.data[i] == 1.0

            if torch.sum(mask) < filter:
                continue
            annotation = {
                'id': i,
                'segmentation': mask.cpu().numpy(),
                'bbox': result.boxes.data[i],
                'score': result.boxes.conf[i]}
            annotation['area'] = annotation['segmentation'].sum()
            annotations.append(annotation)
        return annotations

    @staticmethod
    def filter_masks(annotations):  # filter the overlap mask
        annotations.sort(key=lambda x: x['area'], reverse=True)
        to_remove = set()
        for i in range(len(annotations)):
            a = annotations[i]
            for j in range(i + 1, len(annotations)):
                b = annotations[j]
                if i != j and j not in to_remove and b['area'] < a['area'] and \
                        (a['segmentation'] & b['segmentation']).sum() / b['segmentation'].sum() > 0.8:
                    to_remove.add(j)

        return [a for i, a in enumerate(annotations) if i not in to_remove], to_remove

    @staticmethod
    def _get_bbox_from_mask(mask):
        mask = mask.astype(np.uint8)
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        x1, y1, w, h = cv2.boundingRect(contours[0])
        x2, y2 = x1 + w, y1 + h
        if len(contours) > 1:
            for b in contours:
                x_t, y_t, w_t, h_t = cv2.boundingRect(b)
                # 将多个bbox合并成一个
                x1 = min(x1, x_t)
                y1 = min(y1, y_t)
                x2 = max(x2, x_t + w_t)
                y2 = max(y2, y_t + h_t)
            h = y2 - y1
            w = x2 - x1
        return [x1, y1, x2, y2]

    def plot(self,
             annotations,
             output,
             bbox=None,
             points=None,
             point_label=None,
             mask_random_color=True,
             better_quality=True,
             retina=False,
             withContours=True):
        if isinstance(annotations[0], dict):
            annotations = [annotation['segmentation'] for annotation in annotations]
        result_name = os.path.basename(self.img_path)
        image = self.ori_img
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        original_h = image.shape[0]
        original_w = image.shape[1]
        # for macOS only
        # plt.switch_backend('TkAgg')
        plt.figure(figsize=(original_w / 100, original_h / 100))
        # Add subplot with no margin.
        plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
        plt.margins(0, 0)
        plt.gca().xaxis.set_major_locator(plt.NullLocator())
        plt.gca().yaxis.set_major_locator(plt.NullLocator())

        plt.imshow(image)
        if better_quality:
            if isinstance(annotations[0], torch.Tensor):
                annotations = np.array(annotations.cpu())
            for i, mask in enumerate(annotations):
                mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
                annotations[i] = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((8, 8), np.uint8))
        if self.device == 'cpu':
            annotations = np.array(annotations)
            self.fast_show_mask(
                annotations,
                plt.gca(),
                random_color=mask_random_color,
                bbox=bbox,
                points=points,
                pointlabel=point_label,
                retinamask=retina,
                target_height=original_h,
                target_width=original_w,
            )
        else:
            if isinstance(annotations[0], np.ndarray):
                annotations = torch.from_numpy(annotations)
            self.fast_show_mask_gpu(
                annotations,
                plt.gca(),
                random_color=mask_random_color,
                bbox=bbox,
                points=points,
                pointlabel=point_label,
                retinamask=retina,
                target_height=original_h,
                target_width=original_w,
            )
        if isinstance(annotations, torch.Tensor):
            annotations = annotations.cpu().numpy()
        if withContours:
            contour_all = []
            temp = np.zeros((original_h, original_w, 1))
            for i, mask in enumerate(annotations):
                if isinstance(mask, dict):
                    mask = mask['segmentation']
                annotation = mask.astype(np.uint8)
                if not retina:
                    annotation = cv2.resize(
                        annotation,
                        (original_w, original_h),
                        interpolation=cv2.INTER_NEAREST,
                    )
                contours, hierarchy = cv2.findContours(annotation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                contour_all.extend(iter(contours))
            cv2.drawContours(temp, contour_all, -1, (255, 255, 255), 2)
            color = np.array([0 / 255, 0 / 255, 1.0, 0.8])
            contour_mask = temp / 255 * color.reshape(1, 1, -1)
            plt.imshow(contour_mask)

        save_path = output
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        plt.axis('off')
        fig = plt.gcf()
        plt.draw()

        try:
            buf = fig.canvas.tostring_rgb()
        except AttributeError:
            fig.canvas.draw()
            buf = fig.canvas.tostring_rgb()
        cols, rows = fig.canvas.get_width_height()
        img_array = np.frombuffer(buf, dtype=np.uint8).reshape(rows, cols, 3)
        cv2.imwrite(os.path.join(save_path, result_name), cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR))

    #   CPU post process
    def fast_show_mask(
        self,
        annotation,
        ax,
        random_color=False,
        bbox=None,
        points=None,
        pointlabel=None,
        retinamask=True,
        target_height=960,
        target_width=960,
    ):
        msak_sum = annotation.shape[0]
        height = annotation.shape[1]
        weight = annotation.shape[2]
        # 将annotation 按照面积 排序
        areas = np.sum(annotation, axis=(1, 2))
        sorted_indices = np.argsort(areas)
        annotation = annotation[sorted_indices]

        index = (annotation != 0).argmax(axis=0)
        if random_color:
            color = np.random.random((msak_sum, 1, 1, 3))
        else:
            color = np.ones((msak_sum, 1, 1, 3)) * np.array([30 / 255, 144 / 255, 1.0])
        transparency = np.ones((msak_sum, 1, 1, 1)) * 0.6
        visual = np.concatenate([color, transparency], axis=-1)
        mask_image = np.expand_dims(annotation, -1) * visual

        show = np.zeros((height, weight, 4))
        h_indices, w_indices = np.meshgrid(np.arange(height), np.arange(weight), indexing='ij')
        indices = (index[h_indices, w_indices], h_indices, w_indices, slice(None))
        # 使用向量化索引更新show的值
        show[h_indices, w_indices, :] = mask_image[indices]
        if bbox is not None:
            x1, y1, x2, y2 = bbox
            ax.add_patch(plt.Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, edgecolor='b', linewidth=1))
        # draw point
        if points is not None:
            plt.scatter(
                [point[0] for i, point in enumerate(points) if pointlabel[i] == 1],
                [point[1] for i, point in enumerate(points) if pointlabel[i] == 1],
                s=20,
                c='y',
            )
            plt.scatter(
                [point[0] for i, point in enumerate(points) if pointlabel[i] == 0],
                [point[1] for i, point in enumerate(points) if pointlabel[i] == 0],
                s=20,
                c='m',
            )

        if not retinamask:
            show = cv2.resize(show, (target_width, target_height), interpolation=cv2.INTER_NEAREST)
        ax.imshow(show)

    def fast_show_mask_gpu(
        self,
        annotation,
        ax,
        random_color=False,
        bbox=None,
        points=None,
        pointlabel=None,
        retinamask=True,
        target_height=960,
        target_width=960,
    ):
        msak_sum = annotation.shape[0]
        height = annotation.shape[1]
        weight = annotation.shape[2]
        areas = torch.sum(annotation, dim=(1, 2))
        sorted_indices = torch.argsort(areas, descending=False)
        annotation = annotation[sorted_indices]
        # 找每个位置第一个非零值下标
        index = (annotation != 0).to(torch.long).argmax(dim=0)
        if random_color:
            color = torch.rand((msak_sum, 1, 1, 3)).to(annotation.device)
        else:
            color = torch.ones((msak_sum, 1, 1, 3)).to(annotation.device) * torch.tensor([30 / 255, 144 / 255, 1.0]).to(
                annotation.device)
        transparency = torch.ones((msak_sum, 1, 1, 1)).to(annotation.device) * 0.6
        visual = torch.cat([color, transparency], dim=-1)
        mask_image = torch.unsqueeze(annotation, -1) * visual
        # 按index取数，index指每个位置选哪个batch的数，把mask_image转成一个batch的形式
        show = torch.zeros((height, weight, 4)).to(annotation.device)
        h_indices, w_indices = torch.meshgrid(torch.arange(height), torch.arange(weight), indexing='ij')
        indices = (index[h_indices, w_indices], h_indices, w_indices, slice(None))
        # 使用向量化索引更新show的值
        show[h_indices, w_indices, :] = mask_image[indices]
        show_cpu = show.cpu().numpy()
        if bbox is not None:
            x1, y1, x2, y2 = bbox
            ax.add_patch(plt.Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, edgecolor='b', linewidth=1))
        # draw point
        if points is not None:
            plt.scatter(
                [point[0] for i, point in enumerate(points) if pointlabel[i] == 1],
                [point[1] for i, point in enumerate(points) if pointlabel[i] == 1],
                s=20,
                c='y',
            )
            plt.scatter(
                [point[0] for i, point in enumerate(points) if pointlabel[i] == 0],
                [point[1] for i, point in enumerate(points) if pointlabel[i] == 0],
                s=20,
                c='m',
            )
        if not retinamask:
            show_cpu = cv2.resize(show_cpu, (target_width, target_height), interpolation=cv2.INTER_NEAREST)
        ax.imshow(show_cpu)

    # clip
    @torch.no_grad()
    def retrieve(self, model, preprocess, elements, search_text: str, device) -> int:
        preprocessed_images = [preprocess(image).to(device) for image in elements]
        tokenized_text = self.clip.tokenize([search_text]).to(device)
        stacked_images = torch.stack(preprocessed_images)
        image_features = model.encode_image(stacked_images)
        text_features = model.encode_text(tokenized_text)
        image_features /= image_features.norm(dim=-1, keepdim=True)
        text_features /= text_features.norm(dim=-1, keepdim=True)
        probs = 100.0 * image_features @ text_features.T
        return probs[:, 0].softmax(dim=0)

    def _crop_image(self, format_results):

        image = Image.fromarray(cv2.cvtColor(self.ori_img, cv2.COLOR_BGR2RGB))
        ori_w, ori_h = image.size
        annotations = format_results
        mask_h, mask_w = annotations[0]['segmentation'].shape
        if ori_w != mask_w or ori_h != mask_h:
            image = image.resize((mask_w, mask_h))
        cropped_boxes = []
        cropped_images = []
        not_crop = []
        filter_id = []
        # annotations, _ = filter_masks(annotations)
        # filter_id = list(_)
        for _, mask in enumerate(annotations):
            if np.sum(mask['segmentation']) <= 100:
                filter_id.append(_)
                continue
            bbox = self._get_bbox_from_mask(mask['segmentation'])  # mask 的 bbox
            cropped_boxes.append(self._segment_image(image, bbox))  # 保存裁剪的图片
            # cropped_boxes.append(segment_image(image,mask["segmentation"]))
            cropped_images.append(bbox)  # 保存裁剪的图片的bbox

        return cropped_boxes, cropped_images, not_crop, filter_id, annotations

    def box_prompt(self, bbox):

        assert (bbox[2] != 0 and bbox[3] != 0)
        masks = self.results[0].masks.data
        target_height = self.ori_img.shape[0]
        target_width = self.ori_img.shape[1]
        h = masks.shape[1]
        w = masks.shape[2]
        if h != target_height or w != target_width:
            bbox = [
                int(bbox[0] * w / target_width),
                int(bbox[1] * h / target_height),
                int(bbox[2] * w / target_width),
                int(bbox[3] * h / target_height), ]
        bbox[0] = max(round(bbox[0]), 0)
        bbox[1] = max(round(bbox[1]), 0)
        bbox[2] = min(round(bbox[2]), w)
        bbox[3] = min(round(bbox[3]), h)

        # IoUs = torch.zeros(len(masks), dtype=torch.float32)
        bbox_area = (bbox[3] - bbox[1]) * (bbox[2] - bbox[0])

        masks_area = torch.sum(masks[:, bbox[1]:bbox[3], bbox[0]:bbox[2]], dim=(1, 2))
        orig_masks_area = torch.sum(masks, dim=(1, 2))

        union = bbox_area + orig_masks_area - masks_area
        IoUs = masks_area / union
        max_iou_index = torch.argmax(IoUs)

        return np.array([masks[max_iou_index].cpu().numpy()])

    def point_prompt(self, points, pointlabel):  # numpy 处理

        masks = self._format_results(self.results[0], 0)
        target_height = self.ori_img.shape[0]
        target_width = self.ori_img.shape[1]
        h = masks[0]['segmentation'].shape[0]
        w = masks[0]['segmentation'].shape[1]
        if h != target_height or w != target_width:
            points = [[int(point[0] * w / target_width), int(point[1] * h / target_height)] for point in points]
        onemask = np.zeros((h, w))
        for i, annotation in enumerate(masks):
            mask = annotation['segmentation'] if isinstance(annotation, dict) else annotation
            for i, point in enumerate(points):
                if mask[point[1], point[0]] == 1 and pointlabel[i] == 1:
                    onemask += mask
                if mask[point[1], point[0]] == 1 and pointlabel[i] == 0:
                    onemask -= mask
        onemask = onemask >= 1
        return np.array([onemask])

    def text_prompt(self, text):
        format_results = self._format_results(self.results[0], 0)
        cropped_boxes, cropped_images, not_crop, filter_id, annotations = self._crop_image(format_results)
        clip_model, preprocess = self.clip.load('ViT-B/32', device=self.device)
        scores = self.retrieve(clip_model, preprocess, cropped_boxes, text, device=self.device)
        max_idx = scores.argsort()
        max_idx = max_idx[-1]
        max_idx += sum(np.array(filter_id) <= int(max_idx))
        return np.array([annotations[max_idx]['segmentation']])

    def everything_prompt(self):
        return self.results[0].masks.data
