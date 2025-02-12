#!/usr/bin/env python
# coding: utf-8

import itertools
import xml.etree.ElementTree as ET

import numpy as np
import svg
from metadata import metadata

# TODO: find better places to round floats

###
#
# CONSTANTS
#

# SVG figure size
SIZE = 64

# rounding decimals
DECIMALS = 5

# logo "stroke" width at which the gap between logo "strokes" is equal to this width, too
WIDTH = (np.cos(30 / 180 * np.pi) / 2).round(decimals=DECIMALS)

# zeros for filling
ORIGIN = np.zeros(2)

# for SVG, the origin is top left, so we need to flip the cartesian y-coordinates
INVERT_Y = np.array([1, -1])


###
#
# HELPERS
#


# point manipulation
def polygon(n, rotate=0):
    """
    Calculates the coordinates of a two-dimensional `n`-gon, rotated by an angle `rotate` in radians.

    Returns an numpy array of shape (n, 2).
    """
    angles = 2 * np.pi * np.arange(0, n) / n + rotate
    x = np.cos(angles)
    y = np.sin(angles)
    return np.array([x, y]).T


def flatten(iterable):
    """Shorthand for itertools.chain.from_iterable, as it seems to be the fastest method according to https://stackoverflow.com/a/953097."""
    return itertools.chain.from_iterable(iterable)


def shift(offset, *points):
    """Shift an arbitrary number of points by a given offset."""
    return tuple(p + offset for p in points)


# SVG
def XQ(start, control, end, offset=0, moveto=False):
    """Initialize SVG elements for a line to and through a quadratic Beziér curve."""
    start, control, end = start + offset, control + offset, end + offset
    return (
        svg.M(*start) if moveto else svg.L(*start),
        svg.Q(*control, *end),
    )


def MQ(start, control, end, offset=0):
    """Initialize SVG elements for a line to and through a quadratic Beziér curve. Start with a MOVETO."""
    return XQ(start, control, end, offset, moveto=True)


def LQ(start, control, end, offset=0):
    """Initialize SVG elements for a line to and through a quadratic Beziér curve. Start with a LINETO."""
    return XQ(start, control, end, offset, moveto=False)


def CAP(
    start, end, offset=0, radius=1, rotate=0, moveto=False, large_arc=False, sweep=True
):
    """Initialize a half circle between `start` and `end`."""
    start, end = start + offset, end + offset
    return (
        svg.M(*start) if moveto else svg.L(*start),
        svg.Arc(radius, radius, rotate, large_arc, sweep, *end),
    )


def FixedCAP(start, end):
    """Initialize a half circle with the WIDTH from the module's base config."""
    return CAP(start, end, radius=WIDTH / 2)


def line(start, end, *args, **kwargs):
    """Initialize the SVG elements for a straight line from `start` to `end`."""
    return svg.Path(*args, d=[svg.M(*start), svg.L(*end)], **kwargs)


def get_trigrid(scale=1):
    """Initialize the SVG elements for a triangular grid of diameter 2."""
    u = polygon(6, rotate=np.pi / 2) * scale * INVERT_Y

    roots = np.array([2 * u[2], u[2] + u[3], 2 * u[3], u[3] + u[4], 2 * u[4]]).round(
        decimals=DECIMALS
    )

    lines = [
        line(
            root,
            root * INVERT_Y,
            stroke="lightgray",
            stroke_width=STROKE_WIDTH / 2,
            stroke_linecap="round",
        )
        for root in roots
    ]
    line_group = svg.G(id="trilines", elements=lines)

    trigrid = svg.G(
        id="trigrid",
        elements=[
            line_group,
            svg.Use(href="#trilines", transform="rotate(60)"),
            svg.Use(href="#trilines", transform="rotate(-60)"),
        ],
    )

    return trigrid


def translate(point):
    """Return an option dictionary for SVG translation transformation."""
    x, y = point
    return dict(transform=f"translate({x} {y})")


def save_cleaned_svg(markup, fname):
    """Write the indented `markup` to file `fname`."""
    # to avoid automatic namespace insertions like `ns0:...`, `ns1:...` and so on by the `xml` module,
    # we need to register the namespace "" to the `xmlns` uri
    for ns, uri in [
        ("", "http://www.w3.org/2000/svg"),
        ("cc", "http://creativecommons.org/ns#"),
        ("dc", "http://purl.org/dc/elements/1.1/"),
        ("dcterms", "http://purl.org/dc/terms/"),
        ("foaf", "http://xmlns.com/foaf/0.1/"),
        ("owl", "http://www.w3.org/2002/07/owl#"),
    ]:
        ET.register_namespace(ns, uri)

    # indent the parsed tree
    tree = ET.fromstring(markup)
    ET.indent(tree)

    # alternatives here might be lmxl or BeautifulSoup4(markup, features="xml"),
    # which also needs `lxml` to be installed

    # save to disk
    with open(fname, "wb") as f:
        ET.ElementTree(tree).write(f, encoding="utf-8", xml_declaration=True)


###
#
# POINTS
#

#
# base hexagons
#

# inner spine
i = polygon(6, np.pi / 2) * INVERT_Y

# outer spine
o = 2 * i

# outer "edge-local" hexagon, starts at [1, 0] * WIDTH
up = polygon(6) * INVERT_Y
p = WIDTH * up

# inner "edge-local" hexagon, starts at [0, 1] * WIDTH / 2 / np.cos(30 / 180 * np.pi)
uq = polygon(6, np.pi / 2) / 2 / np.cos(30 / 180 * np.pi) * INVERT_Y
q = WIDTH * uq


#
# outer points, elements and path
#
outer_points = [shift(o[e], p[e], q[e], p[(e + 3) % 6]) for e in range(6)]
outer_elements = [MQ] + 5 * [LQ]
outer_path = [
    element(*[np.array(point).round(decimals=DECIMALS) for point in points])
    for element, points in zip(outer_elements, outer_points)
] + [svg.Z()]


#
# inner points, elements and path
#
inner_points = [
    # edge 0
    shift(o[0], p[5], q[3], p[4]),
    # edge 0 (end) - edge 1 (end)
    shift(o[1], p[0], q[4], p[5]),
    # left arm
    shift(o[2] + p[1], q[0], ORIGIN, q[5]),
    shift(i[2], p[3], q[1], p[2]),
    shift(i[1], (q[1] + q[2]) / 2, (q[4] + q[5]) / 2),
    shift(i[2], p[1], q[4], p[4]),
    shift(o[2] + p[0], q[5], ORIGIN, q[4]),
    # bottom arm
    shift(o[3] + p[2], q[1], ORIGIN, q[0]),
    shift(i[3], (q[1] + q[2]) / 2, (q[4] + q[5]) / 2),
    shift(o[3] + p[1], q[0], ORIGIN, q[5]),
    # center arm
    shift(o[4] + p[3], q[2], ORIGIN, q[1]),
    (p[5], q[2], p[2]),
    shift(i[0], (q[1] + q[2]) / 2, (q[4] + q[5]) / 2),
    (p[1], q[5], p[0]),
    shift(o[4] + p[2], q[1], ORIGIN, q[0]),
    # right arm
    shift((o[5] + o[4]) / 2, p[4], q[2], p[3]),
    shift(i[5], (q[2] + q[3]) / 2, (q[5] + q[0]) / 2),
    shift((o[5] + o[4]) / 2 + p[2], q[1], ORIGIN, q[0]),
    # edge 5
    shift(o[5], p[4], q[2], p[3]),
]

short_arm = [
    LQ,
    FixedCAP,
    LQ,
]

long_arm = [
    LQ,
    *short_arm,
    LQ,
]

inner_elements = [
    MQ,
    LQ,
    *long_arm,
    *short_arm,
    *long_arm,
    *short_arm,
    LQ,
]

inner_path = [
    element(*[np.array(point).round(decimals=DECIMALS) for point in points])
    for element, points in zip(inner_elements, inner_points)
] + [svg.Z()]


###
#
# LOGO
#

LOGO_HALF_SIZE = 2 + WIDTH / 2
LOGO_SIZE = 2 * LOGO_HALF_SIZE


#
# definitions
#
linear_gradient = svg.LinearGradient(
    id="gradient",
    gradientUnits="userSpaceOnUse",
    x1=-LOGO_HALF_SIZE,
    y1=LOGO_HALF_SIZE,
    x2=LOGO_HALF_SIZE,
    y2=-LOGO_HALF_SIZE,
    elements=[
        svg.Stop(
            offset="10%",
            stop_color="#00ffff",  # turquoise
        ),
        svg.Stop(
            offset="90%",
            stop_color="#ff00ff",  # pink
        ),
    ],
)

mask = (
    svg.Mask(
        id="inner",
        elements=[
            # the mask needs to be defined at all point (x, y) in the SVG, so we need to specify this <rect> element
            svg.Rect(
                x=-LOGO_HALF_SIZE,
                y=-LOGO_HALF_SIZE,
                width=LOGO_SIZE,
                height=LOGO_SIZE,
                fill="white",
            ),
            # cutout
            svg.Path(
                d=inner_path,
                fill="black",
            ),
        ],
    ),
)


#
# element arrangement
#
elements = [
    svg.Metadata(text=metadata("logo")),
    svg.Defs(
        elements=[
            linear_gradient,
            mask,
        ]
    ),
    svg.Path(
        d=outer_path,
        mask="url(#inner)",
        fill="url(#gradient)",
    ),
]


#
# SVG
#
s = svg.SVG(
    viewBox=svg.ViewBoxSpec(
        min_x=-LOGO_HALF_SIZE,
        min_y=-LOGO_HALF_SIZE,
        width=LOGO_SIZE,
        height=LOGO_SIZE,
    ),
    width=SIZE,
    height=SIZE,
    elements=elements,
)

save_cleaned_svg(str(s), "logo.svg")


###
#
# BREAKDOWN
#

BREAKDOWN_HALF_SIZE = 3
BREAKDOWN_SIZE = 2 * BREAKDOWN_HALF_SIZE
STROKE_WIDTH = 5e-2
TRIGRID_SCALE = np.sqrt(np.dot(q[0], q[0])).round(decimals=DECIMALS)


#
# definitions
#
marker = svg.Circle(
    id="marker",
    cx=0,
    cy=0,
    r=STROKE_WIDTH,
    stroke="black",
    fill="white",
    stroke_width=STROKE_WIDTH,
)

hexagon_coords = i.flatten().round(decimals=DECIMALS).tolist()
hexagon = svg.Polygon(
    id="hexagon",
    points=hexagon_coords,
    stroke="gray",
    fill="none",
    stroke_width=STROKE_WIDTH / 2,
)

trigrid = get_trigrid(scale=TRIGRID_SCALE)


#
# element arrangement
#

# offsets
o_ = np.append(o, [o[0]], axis=0)
i_ = np.append(i, [i[0]], axis=0)
middle = ((o_[1:] + o_[:-1]) / 2).round(decimals=DECIMALS)
edges = np.concat((np.array([ORIGIN, (o[5] + o[4]) / 2]), i, o)).round(
    decimals=DECIMALS
)
points = np.array(list(flatten(outer_points + inner_points))).round(decimals=DECIMALS)

elements = [
    svg.Metadata(text=metadata("breakdown")),
    svg.Defs(elements=[marker, hexagon, trigrid]),
    svg.G(elements=[svg.Use(href="#trigrid", **translate(point)) for point in edges]),
    svg.G(elements=[svg.Use(href="#hexagon", **translate(point)) for point in middle]),
    svg.G(
        elements=[
            svg.Path(
                d=inner_path,
                stroke="black",
                stroke_width=STROKE_WIDTH,
                fill="none",
            ),
            svg.Path(
                d=outer_path,
                stroke="black",
                stroke_width=STROKE_WIDTH,
                fill="none",
            ),
        ]
    ),
    svg.G(elements=[svg.Use(href="#marker", **translate(point)) for point in points]),
]


#
# SVG
#
s = svg.SVG(
    viewBox=svg.ViewBoxSpec(
        min_x=-BREAKDOWN_HALF_SIZE,
        min_y=-BREAKDOWN_HALF_SIZE,
        width=BREAKDOWN_SIZE,
        height=BREAKDOWN_SIZE,
    ),
    width=SIZE,
    height=SIZE,
    elements=elements,
)

save_cleaned_svg(str(s), "breakdown.svg")
