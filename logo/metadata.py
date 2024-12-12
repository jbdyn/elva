import os
import sys
from posixpath import join  # does not strip empty fragments
from urllib.parse import urljoin  # recognizes fragments

from rdflib import DC, DCTERMS, FOAF, OWL, Graph, Namespace
from rdflib.extras.describer import Describer


def metadata(image, xml_declaration=False):
    # `pretty-xml`rewrites `rdf:Description` with its specified rdf:type,
    # for explicit RDF/XML format, use `xml`
    FORMAT = "pretty-xml"

    ##
    #
    # PREAMBLE
    #

    LANG = "en"

    ##
    # Dublin Core objects
    LOGO_CREATORS = [
        "Technische Universität Berlin",
        "ELVA Team",
        "Jakob Zahn",
    ]
    LOGO_TYPE = "Image"
    LOGO_FORMAT = "image/svg+xml"
    LOGO_BASE_URI = "http://github.com/innocampus/elva/logo/"

    match image:
        case "logo":
            LOGO_SVG = "logo.svg"
            LOGO_TITLE = "ELVA Logo"
            LOGO_DESCRIPTION = (
                "Logo of the ELVA Project of Technische Universität Berlin"
            )
            LOGO_RELATION = join(LOGO_BASE_URI, "breakdown.svg")
        case "breakdown":
            LOGO_SVG = "breakdown.svg"
            LOGO_TITLE = "ELVA Logo Breakdown"
            LOGO_DESCRIPTION = "Breakdown of the logo of the ELVA Project of Technische Universität Berlin"
            LOGO_RELATION = join(LOGO_BASE_URI, "logo.svg")

    LOGO_URI = join(LOGO_BASE_URI, LOGO_SVG)

    ##
    # Creative Commonse BY-NC-SA 4.0 License information
    # compare to https://github.com/creativecommons/cc-legal-tools-data/blob/main/docs/rdf/index.rdf
    CC_UNIT = "by-nc-sa"
    CC_VERSION = "4.0"
    CC_TITLE = "Attribution-NonCommercial-ShareAlike 4.0 International"

    CC_BASE_URI = "http://creativecommons.org"
    CC_NAMESPACE = join(CC_BASE_URI, "ns#")
    CC_LICENSE_CLASS = join(CC_BASE_URI, "license", "")
    CC_LICENSE_UNIT_VERSION = join(CC_BASE_URI, "licenses", CC_UNIT, CC_VERSION, "")
    CC_LEGALCODE = join(CC_LICENSE_UNIT_VERSION, f"legalcode.{LANG}")

    # FOAF resources
    FOAF_LICENSE_BUTTONS = join("http://licensebuttons.net/l/", CC_UNIT, CC_VERSION)

    ##
    #
    # RDF GRAPH PROVISIONING
    #

    g = Graph()
    CC = Namespace(CC_NAMESPACE)
    g.bind("cc", CC)

    ##
    # Dublin Core metadata
    #
    dc = Describer(g, about=LOGO_URI)
    dc.value(DC.title, LOGO_TITLE)
    dc.value(DC.type, LOGO_TYPE)
    dc.value(DC.format, LOGO_FORMAT)
    dc.value(DC.description, LOGO_DESCRIPTION, lang=LANG)
    dc.rel(DC.relation, LOGO_RELATION)
    for creator in LOGO_CREATORS:
        dc.value(DC.creator, creator)

    ##
    # Creative Commonse license <rdf:Description>...</rdf:Description>
    #
    cc = Describer(g, base=CC_BASE_URI, about=CC_LICENSE_UNIT_VERSION)
    cc.rdftype(CC.License)

    # cc namespace
    cc.value(CC.legalcode, CC_LEGALCODE, lang=LANG)
    cc.rel(CC.licenseClass, CC_LICENSE_CLASS)
    cc.rel(CC.permits, urljoin(CC_NAMESPACE, "#DerivateWorks"))
    cc.rel(CC.permits, urljoin(CC_NAMESPACE, "#Distribution"))
    cc.rel(CC.permits, urljoin(CC_NAMESPACE, "#Reproduction"))
    cc.rel(CC.prohibits, urljoin(CC_NAMESPACE, "#CommercialUse"))
    cc.rel(CC.requires, urljoin(CC_NAMESPACE, "#Attribution"))
    cc.rel(CC.requires, urljoin(CC_NAMESPACE, "#Notice"))
    cc.rel(CC.requires, urljoin(CC_NAMESPACE, "#ShareAlike"))

    # dcterms namespace
    cc.value(DCTERMS.LicenseDocument, CC_LEGALCODE, lang=LANG)
    cc.rel(DCTERMS.creator, CC_BASE_URI)
    cc.value(DCTERMS.hasVersion, CC_VERSION)
    cc.value(DCTERMS.identifier, CC_UNIT)
    cc.value(DCTERMS.source, join(CC_BASE_URI, "licenses", CC_UNIT, "3.0", ""))
    cc.value(DCTERMS.title, CC_TITLE, lang=LANG)

    # foaf namespace
    cc.rel(FOAF.logo, join(FOAF_LICENSE_BUTTONS, "80x15.png"))
    cc.rel(FOAF.logo, join(FOAF_LICENSE_BUTTONS, "88x31.png"))

    # owl namespace
    cc.rel(OWL.sameAs, CC_LICENSE_UNIT_VERSION)

    ##
    #
    # RDF GRAPH SERIALIZATION
    #

    content = g.serialize(format=FORMAT)

    if not xml_declaration:
        lines = content.splitlines()[1:]
        content = os.linesep.join(lines)

    return content


if __name__ == "__main__":
    try:
        image = sys.argv[1]
    except IndexError:
        image = "logo"

    print(metadata(image))
