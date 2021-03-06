#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import os
import unittest

import numpy as np
import cv2

from context import imgpheno as ft

IMAGE_SLIPPER = "../examples/images/slipper.jpg"
IMAGES_ERYCINA = (
    "../examples/images/erycina/1.jpg",
    "../examples/images/erycina/2.jpg"
    )
IMAGES_RECTANGLE = (
    "../examples/images/rectangle/100.png",
    "../examples/images/rectangle/45.png",
    "../examples/images/rectangle/90.png"
    )
MAX_SIZE = 500

def scale_max_perimeter(img, m):
    """Return a scaled down image based on a maximum perimeter `m`.

    The perimeter is calculated as image width + height. The original image is
    returned if `m` is None or if the image perimeter is smaller.
    """
    perim = sum(img.shape[:2])
    if m and perim > m:
        rf = float(m) / perim
        img = cv2.resize(img, None, fx=rf, fy=rf)
    return img

def grabcut(img, iters=5, roi=None, margin=5):
    """Run the GrabCut algorithm for segmentation and return the mask."""
    mask = np.zeros(img.shape[:2], np.uint8)
    bgdmodel = np.zeros((1,65), np.float64)
    fgdmodel = np.zeros((1,65), np.float64)
    if not roi:
        roi = (margin, margin, img.shape[1]-margin*2, img.shape[0]-margin*2)
    cv2.grabCut(img, mask, roi, bgdmodel, fgdmodel, iters, cv2.GC_INIT_WITH_RECT)
    return mask

def error(a, p, f):
    """Calculate the error between actual `a` and predicted `p` values.

    The error is calculated with function `f`.
    """
    if isinstance(a, (float,int,long,complex)) and \
            isinstance(p, (float,int,long,complex)):
        return f(a, p)
    elif isinstance(a, (list,tuple,np.ndarray)) and \
            isinstance(p, (list,tuple,np.ndarray)):
        if len(a) == len(p):
            e = 0.0
            for i in range(len(a)):
                e += f(a[i], p[i])
            return e / len(a)
    raise ValueError("Expected numerals or equal length lists thereof")

def mse(a, p):
    """Calculate the mean square error."""
    return abs(p-a) ** 2

def mape(a, p):
    """Calculate the mean absolute percentage error."""
    return abs(p-a) / a

class TestFeatures(unittest.TestCase):
    """Unit tests for the features module."""

    def setUp(self):
        self.base_dir = os.path.dirname(__file__)

    def test_point_dist(self):
        """Test point distance calculation."""
        data = (
            ((0,0),         (8,9),      12.0416),
            ((1,3),         (8,9),      9.2195),
            ((-3,34),       (8,-99),    133.4541),
            ((3.5,34.1),    (8.0,99.6), 65.6544)
        )

        for p1, p2, out in data:
            self.assertEqual( round(ft.point_dist(p1, p2), 4), out )

    def test_color_histograms(self):
        """Test color histograms."""
        im_path = os.path.join(self.base_dir, IMAGE_SLIPPER)
        img = cv2.imread(im_path)
        if img == None or img.size == 0:
            raise SystemError("Failed to read %s" % im_path)

        hists = ft.color_histograms(img)

        # Compare with values obtained with The GIMP.
        self.assertEqual( hists[0][0], 40962 )
        self.assertEqual( hists[0][42], 900 )
        self.assertEqual( hists[1][42], 2303 )
        self.assertEqual( hists[2][42], 1822 )
        self.assertEqual( hists[2][255], 8466 )

    def test_shape_outline(self):
        """Test the shape:outline feature."""
        path = IMAGES_RECTANGLE[2]
        k = 20

        # Object width and height.
        w, h = (300, 100)

        im_path = os.path.join(self.base_dir, path)
        img = cv2.imread(im_path)
        if img == None or img.size == 0:
            raise SystemError("Failed to read %s" % im_path)

        # Perform segmentation.
        mask = grabcut(img, 1, None, 1)
        bin_mask = np.where((mask==cv2.GC_FGD) + (mask==cv2.GC_PR_FGD), 255, 0).astype('uint8')

        # Obtain contours (all points) from the mask.
        contour = ft.get_largest_contour(bin_mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        # Get the outline.
        outline = ft.shape_outline(contour, k)

        # Assert the length of the return value.
        self.assertEqual( len(outline), k )

        # Assert the shape values.
        for x, y in outline:
            delta_x = x[0] - x[1]
            delta_y = y[0] - y[1]
            self.assertLess( error(delta_y, h, mape), 0.0001 )
            self.assertLess( error(delta_x, w, mape), 0.0001 )

    def test_shape_360(self):
        """Test the shape:360 feature.

        Extracts the shape from two slightly rotated versions of the same
        image. Then the medium square error between the two extracted shapes is
        calculated and checked.
        """
        max_error = 0.05

        shape = []
        for i, path in enumerate(IMAGES_ERYCINA):
            im_path = os.path.join(self.base_dir, path)
            img = cv2.imread(im_path)
            if img == None or img.size == 0:
                raise SystemError("Failed to read %s" % im_path)

            # Resize the image if it is larger then the threshold.
            img = scale_max_perimeter(img, MAX_SIZE)

            # Perform segmentation.
            mask = grabcut(img, 5, None, 1)

            # Create a binary mask. Foreground is made white, background black.
            bin_mask = np.where((mask==cv2.GC_FGD) + (mask==cv2.GC_PR_FGD), 255, 0).astype('uint8')

            # Obtain contours (all points) from the mask.
            contour = ft.get_largest_contour(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

            # Fit an ellipse on the contour to get the rotation angle.
            box = cv2.fitEllipse(contour)
            rotation = int(box[2])

            # Extract the shape.
            intersects, center = ft.shape_360(contour, rotation)

            # For each angle save the mean distance from center to contour and
            # the standard deviation for the distances.
            means = []
            sds = []
            for angle in range(0, 360):
                distances = []
                for p in intersects[angle]:
                    d = ft.point_dist(center, p)
                    distances.append(d)

                if len(distances) == 0:
                    mean = 0
                    sd = 0
                else:
                    mean = np.mean(distances, dtype=np.float32)
                    if len(distances) > 1:
                        sd = np.std(distances, ddof=1, dtype=np.float32)
                    else:
                        sd = 0

                means.append(mean)
                sds.append(sd)

            # Normalize and save result.
            means = cv2.normalize(np.array(means), None, -1, 1, cv2.NORM_MINMAX)
            sds = cv2.normalize(np.array(sds), None, -1, 1, cv2.NORM_MINMAX)
            shape.append([means, sds])

        # Check the medium square error for the means.
        self.assertLess(error(shape[0][0].ravel(), shape[1][0].ravel(), mse), max_error)

        # Check the medium square error for the standard deviations.
        self.assertLess(error(shape[0][1].ravel(), shape[1][1].ravel(), mse), max_error)

    def test_contour_properties(self):
        """Test measuring of contour properties."""

        # Object width and height.
        w, h = (300, 100)

        # Object angle for each image.
        angle_exp = (100, 45)

        for i, path in enumerate(IMAGES_RECTANGLE[:2]):
            im_path = os.path.join(self.base_dir, path)
            img = cv2.imread(im_path)
            if img == None or img.size == 0:
                raise SystemError("Failed to read %s" % im_path)

            # Perform segmentation.
            mask = grabcut(img, 1, None, 1)
            bin_mask = np.where((mask==cv2.GC_FGD) + (mask==cv2.GC_PR_FGD), 255, 0).astype('uint8')

            # Get contours and properties.
            contours, hierarchy = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            props = ft.contour_properties(contours, 'all')

            # Check if the properties have the expected values.
            self.assertLess( error(props[0]['Area'],            (w * h), mape), 0.06)
            self.assertLess( error(props[0]['Perimeter'],       (w*2 + h*2), mape), 0.06)
            self.assertLess( error(props[0]['Centroid'][0],     (500/2.0), mape), 0.01)
            self.assertLess( error(props[0]['Centroid'][1],     (300/2.0), mape), 0.01)
            self.assertLess( error(props[0]['Orientation'],     angle_exp[i], mape), 0.01)
            self.assertLess( error(props[0]['EquivDiameter'],   np.sqrt(4 * w * h / np.pi), mape), 0.01)
            self.assertLess( error(props[0]['Extent'],          1, mse), 0.01)
            self.assertLess( error(props[0]['Solidity'],        1, mse), 0.01)

if __name__ == '__main__':
    unittest.main()
