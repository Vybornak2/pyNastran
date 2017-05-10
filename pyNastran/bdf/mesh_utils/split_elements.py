"""
defines:
  - split_line_elements(bdf_model, eids, neids=2,
                        eid_start=1, nid_start=1)
"""
from __future__ import print_function
from six import iteritems
import numpy as np
from pyNastran.bdf.bdf import read_bdf


def split_line_elements(bdf_model, eids, neids=2,
                        eid_start=1, nid_start=1):
    """
    Splits a set of element ids

    Parameters
    ----------
    eids : List[int]
        element ids to split
    neids : int; default=5
        how many elements should a single bar be split into
        min=2
    eid_start : int; default=1
        the starting element id
    nid_start : int; default=1
        the starting node id

    A-----*-----B; neids=2
    A--*--*--*--B; neids=4
    """
    assert neids >= 2, neids
    dx = np.linspace(0., 1., num=neids+1)
    for eid in eids:
        elem = bdf_model.elements[eid]
        print(elem.nodes)
        n1, n2 = elem.nodes
        node1 = bdf_model.nodes[n1]
        node2 = bdf_model.nodes[n2]
        cp = node1.cp
        assert node1.cp == node2.cp
        assert node1.cd == node2.cd
        xyz1 = node1.xyz
        xyz2 = node2.xyz
        dxyz = xyz2 - xyz1
        etype = elem.type

        if etype in ['CBAR', 'CBEAM']:
            pa = elem.pa
            pb = 0

        elem.comment = ''
        comment = str(elem) + '\n'
        for ieid in range(neids):
            dxi = dx[ieid + 1]
            new_xyz = xyz1 + dxyz * dxi
            if dxi < 1.:
                new_node = nid_start
                nid_start += 1
                bdf_model.add_grid(new_node, cp=cp, xyz=new_xyz)
            else:
                new_node = n2
                if etype in ['CBAR', 'CBEAM']:
                    pb = elem.pb

            if etype == 'CONROD':
                nids = [n1, new_node]
                bdf_model.add_conrod(eid_start, elem.mid, nids, elem.A, h=elem.j,
                                     c=elem.c, nsm=elem.nsm, comment=comment)
            elif etype == 'CROD':
                nids = [n1, new_node]
                bdf_model.add_crod(eid_start, elem.mid, nids, comment=comment)
            elif etype == 'CBAR':
                ga = n1
                gb = new_node
                bdf_model.add_cbar(eid_start, elem.pid, ga, gb, elem.x, elem.g0, offt=elem.offt,
                                   pa=pa, pb=pb, wa=elem.wa, wb=elem.wb, comment=comment)
                pa = 0
            elif etype == 'CBEAM':
                ga = n1
                gb = new_node
                bdf_model.add_cbeam(eid_start, elem.pid, ga, gb, elem.x, elem.g0,
                                    offt=elem.offt, bit=elem.bit,
                                    pa=pa, pb=pb,
                                    wa=elem.wa, wb=elem.wb, sa=elem.sa, sb=elem.sb,
                                    comment=comment)
                pa = 0
            else:
                raise NotImplementedError(elem)
            n1 = new_node
            eid_start += 1
            comment = str(eid)
        del bdf_model.elements[eid]
    return eid_start, nid_start


def split_elements(bdf_filename):
    """unimplmented method for splitting elements"""
    model = read_bdf(bdf_filename, xref=True)
    for eid, elem in iteritems(model.elements):
        if elem.type == 'CTRIA3':
            #
            #        3
            #       /|\
            #      / | \
            #     /  |  \
            #    /   4   \
            #   /  /   \  \
            #  / /       \ \
            # 1-------------2
            #
            p1, p2, p3 = elem.get_node_positions()
            #centroid = (p1 + p2 + p3) / 3.

            #
            #      3
            #     /|\
            #    / | \
            #   /  |  \
            #  /   |   \
            # 1----4----2
            #
        elif elem.type == 'CQUAD4':
            #
            #
            # 4---------3
            # | \     / |
            # |   \  /  |
            # |    5    |
            # |  /   \  |
            # |/       \|
            # 1---------2
            #
            # the same thing shown in a rotated view
            #           4
            #          /| \
            #       /   |   \
            #     /     |     \
            #   /       |       \
            # 1---------5---------3
            #   \       |       /
            #     \     |     /
            #       \   |   /
            #         \ | /
            #           2
            #
            # max_area, taper_ratio, area_ratio
            # 4----7----3
            # |    |    |
            # |    |    |
            # 8----9----6
            # |    |    |
            # |    |    |
            # 1----4----2
            #
            # max_interior_angle
            #      4---------3
            #     / \       /
            #    /   \     /
            #   /     \   /
            #  /       \ /
            # 1---------2
            #
            # taper_ratio
            #     4--6--3
            #    /   |   \
            #   /    |    \
            #  /     |     \
            # 1------5------2
            #
            # taper_ratio
            #     4------3
            #    / \    / \
            #   /   \  /   \
            #  /     \/     \
            # 1-------5------2
            #
            # taper_ratio
            #     4------3
            #    / \      \
            #   /   \      \
            #  /     \      \
            # 1-------5------2
            pass
