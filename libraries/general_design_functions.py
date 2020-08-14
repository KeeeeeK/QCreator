from functools import reduce

import gdspy
import numpy as np

import libraries.JJ4q as JJ4q
import libraries.squid3JJ as squid3JJ


# common clases
class coordinates:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class rotations:
    def __init__(self, phi1, phi2):
        self.phi1 = phi1
        self.phi2 = phi2


class Pads:

    def __init__(self, TL_core, TL_gap, TL_ground, coordinate):
        self.coordinate = coordinate
        self.TL_core = TL_core
        self.TL_gap = TL_gap
        self.TL_ground = TL_ground

    @staticmethod
    def contact_pad(x, y, TL_core, TL_gap, TL_ground):
        # fundamental pad constants
        pad_core = 250  # to make pad with 50 Om impedance
        pad_vacuum = 146  # to make pad with 50 Om impedance
        pad_ground = TL_ground
        pad_length = 600
        pad_indent = 50
        edge_indent = 100
        narrowing = 160
        outer_pad_width = (pad_core + (pad_vacuum + pad_ground) * 2)
        inner_pad_width = (pad_core + pad_vacuum * 2)
        outer_TL_width = 2 * (TL_ground + TL_gap) + TL_core
        inner_TL_width = 2 * TL_gap + TL_core

        r1 = gdspy.Polygon([(x, y), (x + outer_TL_width, y),
                            (x + (outer_TL_width + outer_pad_width) / 2, y - narrowing),
                            (x + (outer_TL_width + outer_pad_width) / 2, y - (narrowing + pad_length)),
                            (x - (-outer_TL_width + outer_pad_width) / 2, y - (narrowing + pad_length)),
                            (x - (-outer_TL_width + outer_pad_width) / 2, y - narrowing)])
        x += TL_ground
        r2 = gdspy.Polygon([(x, y), (x + inner_TL_width, y),
                            (x + (inner_TL_width + inner_pad_width) / 2, y - narrowing),
                            (x + (inner_TL_width + inner_pad_width) / 2, y - (narrowing + pad_length - edge_indent)),
                            (x - (-inner_TL_width + inner_pad_width) / 2, y - (narrowing + pad_length - edge_indent)),
                            (x - (-inner_TL_width + inner_pad_width) / 2, y - narrowing)])
        x += TL_gap
        r3 = gdspy.Polygon([(x, y), (x + TL_core, y),
                            (x + (pad_core + TL_core) / 2, y - narrowing),
                            (x + (pad_core + TL_core) / 2, y - (narrowing + pad_length - pad_indent - edge_indent)),
                            (x - (pad_core - TL_core) / 2, y - (narrowing + pad_length - pad_indent - edge_indent)),
                            (x - (pad_core - TL_core) / 2, y - narrowing)])
        return gdspy.boolean(gdspy.boolean(r1, r2, 'not'), r3, 'or'), r1

    @staticmethod
    def generate_ground(Pads_array, sample_size_x, sample_size_y, total_layer, restricted_area_layer):
        edge = 600  # fundamental constant - edge length
        pad_total_length = 760 + 200  # fundamental constant - pad_length+narrowing+200, where 200 is an indent for an orientation checking
        r1 = gdspy.Rectangle((0, 0), (sample_size_x, sample_size_y))
        r2 = gdspy.Rectangle((edge, edge), (sample_size_x - edge, sample_size_y - edge))
        result = gdspy.boolean(r1, r2, 'not')
        restricted_area = result
        for one_pad in Pads_array:
            coord_init_x, coord_init_y = one_pad.coordinate
            TL_core = one_pad.TL_core
            TL_vacuum = one_pad.TL_gap
            TL_ground = one_pad.TL_ground
            outer_TL_width = TL_core + 2 * (TL_ground + TL_vacuum)
            coord_x, coord_y = (coord_init_x - outer_TL_width / 2, coord_init_y)
            pad, restricted_pad = one_pad.contact_pad(coord_x, coord_y, TL_core, TL_vacuum, TL_ground)
            if coord_x < pad_total_length:
                pad.rotate(-np.pi / 2, [coord_init_x, coord_init_y])
                restricted_pad.rotate(-np.pi / 2, [coord_init_x, coord_init_y])
            elif coord_x > sample_size_x - pad_total_length:
                pad.rotate(np.pi / 2, [coord_init_x, coord_init_y])
                restricted_pad.rotate(np.pi / 2, [coord_init_x, coord_init_y])
            elif coord_y > sample_size_y / 2:
                pad.mirror([0, coord_init_y], [sample_size_y, coord_init_y])
                restricted_pad.mirror([0, coord_init_y], [sample_size_y, coord_init_y])
            to_bool = gdspy.Rectangle(pad.get_bounding_box()[0].tolist(), pad.get_bounding_box()[1].tolist())
            result = gdspy.boolean(gdspy.boolean(result, to_bool, 'not'), pad, 'or', layer=total_layer)
            restricted_area = gdspy.boolean(restricted_area, restricted_pad, 'or', layer=restricted_area_layer)
        return result, restricted_area


class Coaxmon:
    def __init__(self, center, r1, r2, r3, R4, outer_ground, total_layer, restricted_area_layer, JJ_layer, Couplers,
                 JJ):
        self.center = center
        self.R1 = r1
        self.R2 = r2
        self.R3 = r3
        self.R4 = R4
        self.outer_ground = outer_ground
        self.Couplers = Couplers
        self.restricted_area_layer = restricted_area_layer
        self.total_layer = total_layer
        self.JJ_layer = JJ_layer
        self.JJ_params = JJ
        self.JJ = None

    def generate_qubit(self):
        ground = gdspy.Round(self.center, self.outer_ground, self.R4, initial_angle=0, final_angle=2 * np.pi)
        restricted_area = gdspy.Round(self.center, self.outer_ground, layer=self.restricted_area_layer)
        core = gdspy.Round(self.center, self.R1, inner_radius=0, initial_angle=0, final_angle=2 * np.pi)
        result = gdspy.boolean(ground, core, 'or', layer=self.total_layer)
        if len(self.Couplers) != 0:
            for Coupler in self.Couplers:
                if Coupler.grounded == True:
                    result = gdspy.boolean(Coupler.generate_coupler(self.center, self.R2, self.outer_ground, self.R4),
                                           result, 'or', layer=self.total_layer)
                else:
                    result = gdspy.boolean(Coupler.generate_coupler(self.center, self.R2, self.R3, self.R4), result,
                                           'or', layer=self.total_layer)
        self.JJ_coordinates = (self.center[0] + self.R1 * np.cos(self.JJ_params['angle_qubit']),
                               self.center[1] + self.R1 * np.sin(self.JJ_params['angle_qubit']))
        JJ, rect = self.generate_JJ()
        result = gdspy.boolean(result, rect, 'or')
        # self.AB1_coordinates = coordinates(self.center.x, self.center.y + self.R4)
        # self.AB2_coordinates = coordinates(self.center.x, self.center.y - self.outer_ground)
        return result, restricted_area, JJ

    def generate_JJ(self):
        self.JJ = squid3JJ.JJ_2(self.JJ_coordinates[0], self.JJ_coordinates[1],
                                self.JJ_params['a1'], self.JJ_params['a2'],
                                self.JJ_params['b1'], self.JJ_params['b2'],
                                self.JJ_params['c1'], self.JJ_params['c2'])
        result = self.JJ.generate_JJ()
        result = gdspy.boolean(result, result, 'or', layer=self.JJ_layer)
        angle = self.JJ_params['angle_JJ']
        # print(self.JJ_coordinates[0],self.JJ_coordinates[1])
        # print((self.JJ_coordinates[0],self.JJ_coordinates[1]))
        result.rotate(angle, (self.JJ_coordinates[0], self.JJ_coordinates[1]))
        rect = gdspy.Rectangle((self.JJ_coordinates[0] - self.JJ.contact_pad_a_outer / 2,
                                self.JJ_coordinates[1] + self.JJ.contact_pad_b_outer),
                               (self.JJ_coordinates[0] + self.JJ.contact_pad_a_outer / 2,
                                self.JJ_coordinates[1] - self.JJ.contact_pad_b_outer), layer=self.total_layer)
        rect.rotate(angle, (self.JJ_coordinates[0], self.JJ_coordinates[1]))
        return result, rect


class QubitCoupler:
    def __init__(self, arc_start, arc_finish, phi, w, grounded=False):
        self.arc_start = arc_start
        self.arc_finish = arc_finish
        self.phi = phi
        self.w = w
        self.grounded = grounded

    def generate_coupler(self, coordinate, r_init, r_final, rect_end):
        # to fix bug
        bug = 5
        result = gdspy.Round(coordinate, r_init, r_final,
                             initial_angle=(self.arc_start) * np.pi, final_angle=(self.arc_finish) * np.pi)
        rect = gdspy.Rectangle((coordinate[0] + r_final - bug, coordinate[1] - self.w / 2),
                               (coordinate[0] + rect_end + bug, coordinate[1] + self.w / 2))
        rect.rotate(self.phi * np.pi, coordinate)
        return gdspy.boolean(result, rect, 'or')


class Airbridge:
    def __init__(self, width, length, padsize, point, angle, line_type=None):
        self.x = point[0]
        self.y = point[1]
        self.angle = angle
        self.padsize = padsize
        self.width = width
        self.length = length
        self.restrictedArea = []
        self.line_type = line_type
        self.start = (None, None)
        self.end = (None, None)

    def generate_bridge(self, Padlayer, Bridgelayer):
        if self.line_type == 'line':
            self.x += (self.length / 2 + self.padsize / 2) * np.cos(self.angle)
            self.y += (self.length / 2 + self.padsize / 2) * np.sin(self.angle)

        # first the two contacts
        contact_1 = gdspy.Rectangle((self.x - self.length / 2 - self.padsize / 2, self.y - self.padsize / 2),
                                    (self.x - self.length / 2 + self.padsize / 2, self.y + self.padsize / 2))
        contact_2 = gdspy.Rectangle((self.x + self.length / 2 - self.padsize / 2, self.y - self.padsize / 2),
                                    (self.x + self.length / 2 + self.padsize / 2, self.y + self.padsize / 2))
        contacts = gdspy.boolean(contact_1, contact_2, 'or', layer=Padlayer)
        contacts.rotate(self.angle, (self.x, self.y))
        # add restricted area for holes
        self.restrictedArea.append(
            gdspy.Rectangle((self.x - self.length / 2 - self.padsize / 2, self.y - self.padsize / 2),
                            (self.x + self.length / 2 + self.padsize / 2, self.y + self.padsize / 2)))
        # now the bridge itself
        bridge = gdspy.Rectangle((self.x - self.length / 2, self.y - self.width / 2),
                                 (self.x + self.length / 2, self.y + self.width / 2), layer=Bridgelayer)
        bridge.rotate(self.angle, (self.x, self.y))

        return [contacts, bridge]


class Feedline:
    def __init__(self, points, core, gap, ground, nodes, total_layer, rectricted_area_layer, R):
        self.core = core
        self.ground = ground
        self.gap = gap
        self.points = points
        self.nodes = nodes
        self._R = R  # fundamental constant
        self.rectricted_area = None
        self.total_layer = total_layer
        self.rectricted_area_layer = rectricted_area_layer
        self.end = self.points[-1]
        self.angle = None

    def generate_feedline(self, corners_type='round'):
        offset = self.gap + (self.core + self.ground) / 2

        self.R1 = self._R - (
                self.core / 2 + self.gap + self.ground / 2)
        self.R2 = np.abs(
            self._R + self.core / 2 + self.gap + self.ground / 2)

        self.R1_new = self._R - (self.core / 2 + self.gap / 2)
        self.R2_new = np.abs(self._R + self.core / 2 + self.gap / 2)

        result = None
        result_ = None
        result_new = None

        if len(self.points) < 3:
            self.points.insert(1, ((self.points[0][0] + self.points[1][0]) / 2,
                                   (self.points[0][1] + self.points[1][1]) / 2))
        new_points = self.points
        # new_points_restricted_line= self.points

        width_restricted_line = 2 * self.ground + 2 * self.gap + self.core
        width_new = self.gap
        offset_new = self.gap + self.core

        if self.R1 > 0:
            for i in range(len(self.points) - 2):
                point1 = self.points[i]
                point2 = self.points[i + 1]
                if i < len(self.points) - 3:
                    point3 = ((self.points[i + 1][0] + self.points[i + 2][0]) / 2,
                              (self.points[i + 1][1] + self.points[i + 2][1]) / 2)
                else:
                    point3 = new_points[-1]
                self.points[i + 1] = ((self.points[i + 1][0] + self.points[i + 2][0]) / 2,
                                      (self.points[i + 1][1] + self.points[i + 2][1]) / 2)
                if corners_type is 'round':
                    vector1 = np.asarray(new_points[i + 1][:]) - new_points[i][:]
                    vector2 = np.asarray(new_points[i + 2][:]) - new_points[i + 1][:]
                    vector_prod = vector1[0] * vector2[1] - vector1[1] * vector2[0]
                    if vector_prod < 0:
                        line = gdspy.FlexPath([point1, point2, point3],
                                              [self.ground, self.core,
                                               self.ground], offset, ends=["flush", "flush", "flush"],
                                              corners=["circular bend", "circular bend", "circular bend"],
                                              bend_radius=[self.R1, self._R, self.R2], precision=0.001, layer=0)
                        rectricted_line = gdspy.FlexPath([point1, point2, point3], width_restricted_line, offset=0,
                                                         ends="flush", corners="circular bend", bend_radius=self._R,
                                                         precision=0.001, layer=1)
                        line_new = gdspy.FlexPath([point1, point2, point3], [width_new, width_new], offset=offset_new,
                                                  ends=["flush", "flush"], corners=["circular bend", "circular bend"],
                                                  bend_radius=[self.R1_new, self.R2_new], precision=0.001, layer=2)

                        # rectricted_line = gdspy.FlexPath([point1, point2, point3], width_restricted_line, offset=0,  ends="flush",  corners="circular bend",bend_radius= self._R, precision=0.001, layer=1)

                        # self.end = line.x
                    else:
                        line = gdspy.FlexPath([point1, point2, point3],
                                              [self.ground, self.core,
                                               self.ground], offset, ends=["flush", "flush", "flush"],
                                              corners=["circular bend", "circular bend", "circular bend"],
                                              bend_radius=[self.R2, self._R, self.R1], precision=0.001, layer=0)
                        rectricted_line = gdspy.FlexPath([point1, point2, point3], width_restricted_line, offset=0,
                                                         ends="flush", corners="circular bend", bend_radius=self._R,
                                                         precision=0.001, layer=1)
                        line_new = gdspy.FlexPath([point1, point2, point3], [width_new, width_new], offset=offset_new,
                                                  ends=["flush", "flush"], corners=["circular bend", "circular bend"],
                                                  bend_radius=[self.R2_new, self.R1_new], precision=0.001, layer=2)

                        # self.end = line.x
                    result = gdspy.boolean(line, result, 'or', layer=self.total_layer)
                    result_ = gdspy.boolean(rectricted_line, result_, 'or', layer=self.rectricted_area_layer)
                    result_new = gdspy.boolean(line_new, result_new, 'or', layer=2)
                    # self.rectricted_area = gdspy.boolean(rectricted_line, self.rectricted_area, 'or', layer = self.rectricted_area_layer)

                    # result= line, rectricted_line
                else:
                    line = gdspy.FlexPath([point1, point2, point3],
                                          [self.ground, self.core,
                                           self.ground], offset, ends=["flush", "flush", "flush"],
                                          precision=0.001, layer=0)
                    # self.end = line.x
                    rectricted_line = gdspy.FlexPath([point1, point2, point3],
                                                     width_restricted_line, offset=0, ends="flush",
                                                     precision=0.001, layer=1)

                    line_new = gdspy.FlexPath([point1, point2, point3],
                                              [width_new, width_new], offset=offset_new, ends=["flush", "flush"],
                                              precision=0.001, layer=2)

                    # result= line, rectricted_line
                    result = gdspy.boolean(line, result, 'or', layer=self.total_layer)
                    result_ = gdspy.boolean(rectricted_line, result_, 'or', layer=self.rectricted_area_layer)
                    result_new = gdspy.boolean(line_new, result_new, 'or', layer=2)

                    # self.rectricted_area = gdspy.boolean(rectricted_line, self.rectricted_area, 'or', layer = self.rectricted_area_layer)

        else:
            print('R small < 0')
            result = 0
            result_ = 0
            result_new = 0
        vector2_x = point3[0] - point2[0]
        vector2_y = point3[1] - point2[1]
        if vector2_x != 0 and vector2_x >= 0:
            tang_alpha = vector2_y / vector2_x
            self.angle = np.arctan(tang_alpha)
        elif vector2_x != 0 and vector2_x < 0:
            tang_alpha = vector2_y / vector2_x
            self.angle = np.arctan(tang_alpha) + np.pi
        elif vector2_x == 0 and vector2_y > 0:
            self.angle = np.pi / 2
        elif vector2_x == 0 and vector2_y < 0:
            self.angle = -np.pi / 2
        else:
            print("something is wrong in angle")
        return result, result_, result_new

    def generate_end(self, end):
        if end['type'] == 'open':
            return self.generate_open_end(end)
        if end['type'] == 'fluxline':
            return self.generate_fluxline_end(end)

    def generate_fluxline_end(self, end):
        JJ = end['JJ']
        length = end['length']
        width = end['width']
        point1 = JJ.rect1
        point2 = JJ.rect2
        result = None
        # rect_to_remove = gdspy.Rectangle((),
        #                                  ())
        for point in [point1, point2]:
            line = gdspy.Rectangle((point[0] - width / 2, point[1]),
                                   (point[0] + width / 2, point[1] - length))
            result = gdspy.boolean(line, result, 'or', layer=6)
        # result = gdspy.boolean(line1,line2,'or',layer=self.total_layer)
        path1 = gdspy.Polygon([(point1[0] + width / 2, point1[1] - length), (point1[0] - width / 2, point1[1] - length),
                               (self.end[0] + (self.core / 2 + self.gap + width) * np.cos(self.angle + np.pi / 2),
                                self.end[1] + (self.core / 2 + self.gap + width) * np.sin(self.angle + np.pi / 2)),
                               (self.end[0] + (self.core / 2 + self.gap) * np.cos(self.angle + np.pi / 2),
                                self.end[1] + (self.core / 2 + self.gap) * np.sin(self.angle + np.pi / 2))])

        result = gdspy.boolean(path1, result, 'or', layer=6)

        path2 = gdspy.Polygon([(point2[0] + width / 2, point2[1] - length), (point2[0] - width / 2, point2[1] - length),
                               (self.end[0] + (self.core / 2) * np.cos(self.angle + np.pi / 2),
                                self.end[1] + (self.core / 2) * np.sin(self.angle + np.pi / 2)),
                               (self.end[0] + self.core / 2 * np.cos(self.angle + 3 * np.pi / 2),
                                self.end[1] + (self.core / 2) * np.sin(self.angle + 3 * np.pi / 2))])
        result = gdspy.boolean(path2, result, 'or', layer=6)

        # if end['type'] != 'coupler':
        restricted_area = gdspy.Polygon([(point1[0] - width / 2, point1[1]),
                                         (point2[0] + width / 2 + self.gap, point2[1]),
                                         (point2[0] + width / 2 + self.gap, point2[1] - length),
                                         (self.end[0] + (self.core / 2 + self.gap) * np.cos(
                                             self.angle + 3 * np.pi / 2),
                                          self.end[1] + (self.core / 2 + self.gap) * np.sin(
                                              self.angle + 3 * np.pi / 2)),
                                         (self.end[0] + (self.core / 2 + self.gap + width) * np.cos(
                                             self.angle + np.pi / 2),
                                          self.end[1] + (self.core / 2 + self.gap + width) * np.sin(
                                              self.angle + np.pi / 2)),
                                         (point1[0] - width / 2, point1[1] - length)],
                                        layer=self.rectricted_area_layer)
        # else:
        #
        return result, restricted_area, restricted_area

    def generate_open_end(self, end):
        end_gap = end['gap']
        end_ground_length = end['ground_width']
        x_begin = self.end[0]
        y_begin = self.end[1]

        restricted_area = gdspy.Rectangle((x_begin - self.core / 2 - self.gap - self.ground, y_begin),
                                          (x_begin + self.core / 2 + self.gap + self.ground,
                                           y_begin + end_gap + end_ground_length))
        rectangle_for_removing = gdspy.Rectangle((x_begin - self.core / 2 - self.gap, y_begin),
                                                 (x_begin + self.core / 2 + self.gap, y_begin + end_gap))
        total = gdspy.boolean(restricted_area, rectangle_for_removing, 'not')
        total.rotate(-np.pi / 2 + self.angle, self.end)
        restricted_area.rotate(-np.pi / 2 + self.angle, self.end)
        rectangle_for_removing.rotate(-np.pi / 2 + self.angle, self.end)
        return total, restricted_area, rectangle_for_removing


class Narrowing:

    def __init__(self, x, y, core1, gap1, ground1, core2, gap2, ground2, h, rotation):
        self._x_begin = x
        self._y_begin = y

        self.first_core = core1
        self.first_gap = gap1
        self.first_ground = ground1

        self.second_core = core2
        self.second_gap = gap2
        self.second_ground = ground2
        self._h = h

        self._rotation = rotation

    def generate_narrowing(self):

        x_end = self._x_begin - self._h
        y_end = self._y_begin
        result = None

        points_for_poly1 = [(self._x_begin, self._y_begin + self.first_core / 2 + self.first_gap + self.first_ground),
                            (self._x_begin, self._y_begin + self.first_core / 2 + self.first_gap),
                            (x_end, y_end + self.second_core / 2 + self.second_gap),
                            (x_end, y_end + self.second_core / 2 + self.second_gap + self.second_ground)]

        points_for_poly2 = [(self._x_begin, self._y_begin + self.first_core / 2),
                            (self._x_begin, self._y_begin - self.first_core / 2),
                            (x_end, y_end - self.second_core / 2),
                            (x_end, y_end + self.second_core / 2)]

        points_for_poly3 = [(self._x_begin, self._y_begin - (self.first_core / 2 + self.first_gap + self.first_ground)),
                            (self._x_begin, self._y_begin - (self.first_core / 2 + self.first_gap)),
                            (x_end, y_end - (self.second_core / 2 + self.second_gap)),
                            (x_end, y_end - (self.second_core / 2 + self.second_gap + self.second_ground))]

        points_for_restricted_area = [
            (self._x_begin, self._y_begin + self.first_core / 2 + self.first_gap + self.first_ground),
            (x_end, y_end + self.second_core / 2 + self.second_gap + self.second_ground),
            (x_end, y_end - (self.second_core / 2 + self.second_gap + self.second_ground)),
            (self._x_begin, self._y_begin - (self.first_core / 2 + self.first_gap + self.first_ground))]

        restricted_area = gdspy.Polygon(points_for_restricted_area)

        poly1 = gdspy.Polygon(points_for_poly1)
        poly2 = gdspy.Polygon(points_for_poly2)
        poly3 = gdspy.Polygon(points_for_poly3)

        if self._rotation == 0:

            result = poly1, poly2, poly3

        else:

            poly1_ = poly1.rotate(angle=self._rotation, center=(self._x_begin, self._y_begin))
            poly2_ = poly2.rotate(angle=self._rotation, center=(self._x_begin, self._y_begin))
            poly3_ = poly3.rotate(angle=self._rotation, center=(self._x_begin, self._y_begin))
            restricted_area.rotate(angle=self._rotation, center=(self._x_begin, self._y_begin))
            result = poly1_, poly2_, poly3_
            polygon_to_remove = gdspy.boolean(restricted_area, result, 'not', layer=2)
        return result, restricted_area, polygon_to_remove


class IlyaCoupler:
    def __init__(self, core, gap, ground, Coaxmon1, Coaxmon2, JJ_params, squid_params, total_layer,
                 restricted_area_layer, JJ_layer, layer_to_remove):
        self.core = core
        self.gap = gap
        self.ground = ground
        self.Coaxmon1 = Coaxmon1
        self.Coaxmon2 = Coaxmon2
        self.total_layer = total_layer
        self.restricted_area_layer = restricted_area_layer
        self.angle = None
        self.JJ_layer = JJ_layer
        self.layer_to_remove = layer_to_remove
        self.JJ_params = JJ_params
        self.squid_params = squid_params

    def generate_coupler(self):
        vector2_x = self.Coaxmon2.center[0] - self.Coaxmon1.center[0]
        vector2_y = self.Coaxmon2.center[1] - self.Coaxmon1.center[1]
        if vector2_x != 0 and vector2_x >= 0:
            tang_alpha = vector2_y / vector2_x
            self.angle = np.arctan(tang_alpha)
        elif vector2_x != 0 and vector2_x < 0:
            tang_alpha = vector2_y / vector2_x
            self.angle = np.arctan(tang_alpha) + np.pi
        elif vector2_x == 0 and vector2_y > 0:
            self.angle = np.pi / 2
        elif vector2_x == 0 and vector2_y < 0:
            self.angle = -np.pi / 2
        bug = 3  # there is a bug
        points = [(self.Coaxmon1.center[0] + (self.Coaxmon1.R4 - bug) * np.cos(self.angle),
                   self.Coaxmon1.center[1] + (self.Coaxmon1.R4 - bug) * np.sin(self.angle)),
                  (self.Coaxmon2.center[0] + (self.Coaxmon1.R4 - bug) * np.cos(self.angle + np.pi),
                   self.Coaxmon2.center[1] + (self.Coaxmon1.R4 - bug) * np.sin(self.angle + np.pi))]
        line = Feedline(points, self.core, self.gap, self.ground, None, self.total_layer, self.restricted_area_layer,
                        100)
        line = line.generate_feedline()
        JJ1 = self.generate_JJ()
        self.JJ_params['indent'] = np.abs(self.Coaxmon2.center[1] - self.Coaxmon1.center[1]) + np.abs(
            self.Coaxmon2.center[0] -
            self.Coaxmon1.center[0]) - 2 * self.Coaxmon1.R4 - self.JJ_params['indent']
        JJ2 = self.generate_JJ()
        squid = self.generate_squid()
        JJ_0 = gdspy.boolean(JJ1[0], JJ2[0], 'or', layer=self.JJ_layer)
        JJ_1 = gdspy.boolean(JJ1[1], JJ2[1], 'or', layer=6)
        JJ_2 = gdspy.boolean(JJ1[2], JJ2[2], 'or', layer=self.layer_to_remove)

        JJ_0 = gdspy.boolean(JJ_0, squid[0], 'or', layer=self.JJ_layer)
        JJ_1 = gdspy.boolean(JJ_1, squid[1], 'or', layer=6)
        # result = gdspy.boolean(JJ[1],line,'or',layer=self.total_layer)
        return line, [JJ_0, JJ_1, JJ_2]

    def generate_JJ(self):
        self.JJ_params['x'] = self.Coaxmon1.center[0] + (self.Coaxmon1.R4 + self.JJ_params['indent']) * np.cos(
            self.angle)
        if self.Coaxmon1.center[0] != self.Coaxmon2.center[0]:
            self.JJ_params['y'] = self.Coaxmon1.center[1] + (self.Coaxmon1.R4 +
                                                             self.JJ_params['indent']) * np.sin(self.angle) + (
                                          self.core / 2 + self.gap / 2)
        else:
            self.JJ_params['y'] = self.Coaxmon1.center[1] + (self.Coaxmon1.R4 + self.JJ_params['indent']) * np.sin(
                self.angle)
        # print(self.angle)
        self.JJ = JJ4q.JJ_1(self.JJ_params['x'], self.JJ_params['y'],
                            self.JJ_params['a1'], self.JJ_params['a2'],
                            )
        result = self.JJ.generate_JJ()
        result = gdspy.boolean(result, result, 'or', layer=self.JJ_layer)
        angle = self.JJ_params['angle_JJ']
        result.rotate(angle, (self.JJ_params['x'], self.JJ_params['y']))
        indent = 1
        rect1 = gdspy.Rectangle((self.JJ_params['x'] - self.JJ.contact_pad_a / 2,
                                 self.JJ_params['y'] + indent),
                                (self.JJ_params['x'] + self.JJ.contact_pad_a / 2,
                                 self.JJ_params['y'] - self.JJ.contact_pad_b + indent), layer=6)
        rect2 = gdspy.Rectangle((self.JJ.x_end - self.JJ.contact_pad_a / 2,
                                 self.JJ.y_end - 1),
                                (self.JJ.x_end + self.JJ.contact_pad_a / 2,
                                 self.JJ.y_end - self.JJ.contact_pad_b - indent), layer=6)
        if self.Coaxmon1.center[0] != self.Coaxmon2.center[0]:
            poly1 = gdspy.Polygon([(self.JJ_params['x'] - self.JJ.contact_pad_a / 2,
                                    self.JJ_params['y'] + indent),
                                   (self.JJ_params['x'] - self.JJ.contact_pad_a / 2,
                                    self.JJ_params['y'] + indent - self.JJ.contact_pad_b),
                                   (self.JJ_params['x'] - self.JJ.contact_pad_a - indent,
                                    self.Coaxmon1.center[1] - self.core / 2),
                                   (self.JJ_params['x'] - self.JJ.contact_pad_a - indent,
                                    self.Coaxmon1.center[1] + self.core / 2)
                                   ])
            poly2 = gdspy.Polygon([(self.JJ.x_end + self.JJ.contact_pad_a / 2,
                                    self.JJ.y_end - indent - self.JJ.contact_pad_b),
                                   (self.JJ.x_end + self.JJ.contact_pad_a / 2,
                                    self.JJ.y_end - indent),
                                   (self.JJ.x_end + self.JJ.contact_pad_a + indent,
                                    self.Coaxmon1.center[1] + self.core / 2),
                                   (self.JJ.x_end + self.JJ.contact_pad_a + indent,
                                    self.Coaxmon1.center[1] - self.core / 2)
                                   ])
        else:
            poly1 = []
            poly2 = []
        rect = gdspy.boolean(rect1, [rect2, poly1, poly2], 'or', layer=6)
        rect.rotate(angle, (self.JJ_params['x'], self.JJ_params['y']))
        to_remove = gdspy.Polygon(self.JJ.points_to_remove, layer=self.layer_to_remove)
        to_remove.rotate(angle, (self.JJ_params['x'], self.JJ_params['y']))
        return result, rect, to_remove

    def generate_squid(self):
        # print(self.squid_params)
        self.squid = squid3JJ.JJ_2(self.squid_params['x'],
                                   self.squid_params['y'],
                                   self.squid_params['a1'], self.squid_params['a2'],
                                   self.squid_params['b1'], self.squid_params['b2'],
                                   self.squid_params['c1'], self.squid_params['c2'])
        squid = self.squid.generate_JJ()
        rect = gdspy.Rectangle((self.squid_params['x'] - self.squid.contact_pad_a_outer / 2,
                                self.squid_params['y'] + 0 * self.squid.contact_pad_b_outer / 2),
                               (self.squid_params['x'] + self.squid.contact_pad_a_outer / 2,
                                self.squid_params['y'] - self.squid.contact_pad_b_outer), layer=self.total_layer)

        if self.Coaxmon1.center[0] == self.Coaxmon2.center[0]:
            path1 = gdspy.Polygon([(self.squid_params['x'], self.squid_params['y']),
                                   (self.Coaxmon1.center[0], self.squid_params['y']),
                                   (self.Coaxmon1.center[0], self.squid_params['y'] - self.squid.contact_pad_b_outer),
                                   (self.squid_params['x'], self.squid_params['y'] - self.squid.contact_pad_b_outer)])
            rect = gdspy.boolean(rect, path1, 'or', layer=self.total_layer)

        # point1 =
        squid = gdspy.boolean(squid, squid, 'or', layer=self.JJ_layer)
        squid.rotate(self.squid_params['angle'], (self.squid_params['x'],
                                                  self.squid_params['y']))
        return squid, rect


class Fluxonium:
    def __init__(self, center, distance, rectang_params, gap, ground_width):
        """
        :param center: center of fluxonium like (x_coordinate, y_coordinate)
        :param distance: distance from center to the borders of inner rectangles
        :param rectang_params: parameters like (width_rectang,height_rectang)
        :param gap: distance between inner rectangles and ground
        :param ground_width: width of ground
        """
        self.center = center
        self.distance = distance
        self.rectang_params = rectang_params
        self.gap = gap
        self.ground = ground_width

    def generate_fluxonium(self):
        half_length_x = self.distance + self.rectang_params[0] + self.gap + self.ground
        half_length_y = self.rectang_params[1] / 2 + self.gap + self.ground

        ground = gdspy.Rectangle((self.center[0] - half_length_x, self.center[1] - half_length_y),
                                 (self.center[0] + half_length_x, self.center[1] + half_length_y))
        inner_rectangles = [
            gdspy.Rectangle(
                (self.center[0] - self.distance - self.rectang_params[0], self.center[1] - self.rectang_params[1] / 2),
                (self.center[0] - self.distance, self.center[1] + self.rectang_params[1] / 2)),
            gdspy.Rectangle(
                (self.center[0] + self.distance, self.center[1] - self.rectang_params[1] / 2),
                (self.center[0] + self.distance + self.rectang_params[0], self.center[1] + self.rectang_params[1] / 2))
        ]
        empty_rectangle = gdspy.Rectangle((self.center[0] - self.distance - self.rectang_params[0] - self.gap,
                                           self.center[1] - self.rectang_params[1] / 2 - self.gap),
                                          (self.center[0] + self.distance + self.rectang_params[0] + self.gap,
                                           self.center[1] + self.rectang_params[1] / 2 + self.gap))

        result = gdspy.boolean(ground, empty_rectangle, 'not')
        result = gdspy.boolean(result, inner_rectangles[0], 'or')
        result = gdspy.boolean(result, inner_rectangles[1], 'or')
        return result

    def generate_jj(self, left_rect_param, right_rect_param, cap_param,
                    holder_width, fastener_height, jj_width, triangle_side, layer):
        bottom = self.center[1] - self.rectang_params[1] / 2
        holders = [
            gdspy.Rectangle(
                (self.center[0] - self.distance, bottom),
                (self.center[0] - self.distance - holder_width, bottom + self.rectang_params[1]), layer=layer),
            gdspy.Rectangle(
                (self.center[0] + self.distance, bottom),
                (self.center[0] + self.distance + holder_width, bottom + self.rectang_params[1]), layer=layer)
        ]
        fasteners = [
            gdspy.Rectangle(
                (self.center[0] - jj_width / 2, bottom),
                (self.center[0] - self.distance, bottom + fastener_height), layer=layer),
            gdspy.Rectangle(
                (self.center[0] + jj_width / 2, bottom),
                (self.center[0] + self.distance, bottom + fastener_height), layer=layer)
        ]
        left_rect = gdspy.Rectangle(
            (self.center[0] - jj_width / 2, bottom + left_rect_param[1]),
            (self.center[0] - jj_width / 2 + left_rect_param[0], bottom), layer=layer)
        right_rect = gdspy.Rectangle(
            (self.center[0] + jj_width / 2, bottom + right_rect_param[1]),
            (self.center[0] + jj_width / 2 - right_rect_param[0], bottom), layer=layer)
        cap = gdspy.Rectangle(
            (self.center[0] + jj_width / 2 - right_rect_param[0], bottom + right_rect_param[1] - cap_param[1]),
            (self.center[0] + jj_width / 2 - right_rect_param[0] - cap_param[0], bottom + right_rect_param[1]),
            layer=layer)
        triangles = [
            _generate_rectangular_triangle(
                (self.center[0] + jj_width / 2 - right_rect_param[0], bottom + right_rect_param[1] - cap_param[1]),
                triangle_side, to_x=False, to_y=False, layer=layer),
            _generate_rectangular_triangle(
                (self.center[0] + jj_width / 2, bottom + fastener_height),
                triangle_side, to_x=True, to_y=True, layer=layer),
            _generate_rectangular_triangle(
                (self.center[0] - jj_width / 2, bottom + fastener_height),
                triangle_side, to_x=False, to_y=True, layer=layer)
        ]
        empty_triangle = _generate_rectangular_triangle(
            (self.center[0] + jj_width / 2 - right_rect_param[0], bottom),
            triangle_side, to_x=True, to_y=True, layer=layer)
        all_figures = holders + fasteners + [left_rect, right_rect, cap] + triangles
        result = reduce(lambda x, y: gdspy.boolean(y, x, 'or', layer=layer), all_figures, None)
        return gdspy.boolean(result, empty_triangle, 'not', layer=layer)

    def generate_inductivity(self, N, d, fastener_height, side, distance1, distance2, gap, width1, width2, ledge,
                             layer):
        """pay attention that fastener_height must be the same as in generate_jj"""
        bottom = self.center[1] - self.rectang_params[1] / 2 + fastener_height
        left_squares, right_squares = map(lambda sign: [gdspy.Rectangle(
            (self.center[0] + sign * distance1, bottom + i * (d + side)),
            (self.center[0] + sign * (distance1 + side), bottom + i * (d + side) + side),
            layer=layer
        ) for i in range(N)], [+1, -1])
        result = reduce(lambda x, y: gdspy.boolean(y, x, 'or', layer=layer), left_squares + right_squares, None)
        bottom += N * (side + d)
        # going from bottom to top
        rectangles = [
            gdspy.Rectangle(
                (self.center[0] - distance2 - width2, bottom),
                (self.center[0] - distance1, bottom + width1),
                layer=layer),
            gdspy.Rectangle(
                (self.center[0] + distance2 + width2, bottom),
                (self.center[0] + distance1, bottom + width1),
                layer=layer)
        ]
        bottom += width1
        rectangles += [
            gdspy.Rectangle(
                (self.center[0] - distance2 - width2, bottom),
                (self.center[0] - distance2, bottom + 2 * gap + width1),
                layer=layer),
            gdspy.Rectangle(
                (self.center[0] + distance2 + width2, bottom),
                (self.center[0] + distance2, bottom + 2 * gap + width1),
                layer=layer)
        ]
        bottom += 2 * gap + width1
        rectangles.append(gdspy.Rectangle(
            (self.center[0] - distance2 - width2, bottom),
            (self.center[0] + 1 / 2 * width2, bottom + width2),
            layer=layer))
        rectangles.append(gdspy.Rectangle(
            (self.center[0] + distance2, bottom),
            (self.center[0] + distance2 + width2, bottom + width2 + ledge),
            layer=layer))
        # center rectangles
        bottom += width2
        rectangles.append(gdspy.Rectangle(
            (self.center[0] - width2 / 2, bottom),
            (self.center[0] + width2 / 2, bottom + ledge),
            layer=layer))
        bottom -= gap + width1 + width2
        rectangles.append(gdspy.Rectangle(
            (self.center[0] - distance2, bottom),
            (self.center[0] + distance2, bottom + width1),
            layer=layer))
        return reduce(lambda x, y: gdspy.boolean(y, x, 'or', layer=layer), rectangles, result)


def _generate_rectangular_triangle(vertex, side, to_x: bool = True, to_y: bool = True, layer=None):
    x, y = map(lambda to_z: side * {True: +1, False: -1}[to_z], [to_x, to_y])
    return gdspy.Polygon([
        vertex,
        (vertex[0] + x, vertex[1]),
        (vertex[0], vertex[1] + y)],
        layer=layer)
