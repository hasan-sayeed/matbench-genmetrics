import logging

import numpy as np
from matminer.featurizers.composition.composite import ElementProperty
from matminer.featurizers.site.fingerprint import CrystalNNFingerprint
from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.core.structure import Structure
from scipy.spatial.distance import cdist, pdist, squareform
from tqdm import tqdm
from tqdm.notebook import tqdm as ipython_tqdm

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)

sm = StructureMatcher(stol=0.5, ltol=0.3, angle_tol=10.0)

# https://stackoverflow.com/a/58102605/13697228
is_notebook = hasattr(__builtins__, "__IPYTHON__")


def dummy_tqdm(x, **kwargs):  # noqa: E731
    pass


def get_tqdm(verbose):
    if verbose:
        return ipython_tqdm if is_notebook else tqdm
    else:
        return dummy_tqdm


def structure_matcher(s1: Structure, s2: Structure):
    return sm.fit(s1, s2)


pairwise_match_fn_dict = {"StructureMatcher": structure_matcher}


def structure_pairwise_match_matrix(
    test_structures,
    gen_structures,
    match_type="StructureMatcher",
    verbose=False,
    symmetric=False,
):
    # TODO: replace with group_structures to be faster
    pairwise_match_fn = pairwise_match_fn_dict[match_type]
    match_matrix = np.zeros((len(test_structures), len(gen_structures)))
    if verbose:
        logger.info(f"Computing {match_type} match matrix pairwise")

    my_tqdm = get_tqdm(verbose)
    for i, ts in enumerate(my_tqdm(test_structures)):
        for j, gs in enumerate(gen_structures):
            if not symmetric or (symmetric and i < j):
                match_matrix[i, j] = pairwise_match_fn(ts, gs)
    if symmetric:
        match_matrix = match_matrix + match_matrix.T
    return match_matrix


CompFP = ElementProperty.from_preset("magpie")


def cdvae_cov_comp_fingerprints(structures, verbose=False):
    if verbose:
        logger.info("Computing composition fingerprints")
    my_tqdm = get_tqdm(verbose)
    return [CompFP.featurize(s.composition) for s in my_tqdm(structures)]


CrystalNNFP = CrystalNNFingerprint.from_preset("ops")
bva = BVAnalyzer()


def cdvae_cov_struct_fingerprints(structures, verbose=False):
    if verbose:
        logger.info("Computing structure fingerprints")
    my_tqdm = get_tqdm(verbose)
    struct_fps = []
    for s in my_tqdm(structures):
        site_fps = [CrystalNNFP.featurize(s, i) for i in range(len(s))]
        struct_fp = np.array(site_fps).mean(axis=0)
        struct_fps.append(struct_fp)
    return struct_fps


def cdvae_cov_dist_matrix(
    test_structures,
    gen_structures,
    composition_only=False,
    symmetric=False,
    verbose=False,
):
    if verbose:
        type_str = "composition" if composition_only else "structure"
        logger.info(f"Computing {type_str} distance matrix")
    fingerprint_fn = (
        cdvae_cov_comp_fingerprints
        if composition_only
        else cdvae_cov_struct_fingerprints
    )
    test_comp_fps = fingerprint_fn(test_structures)
    if symmetric:
        dm = squareform(pdist(test_comp_fps))
    else:
        gen_comp_fps = fingerprint_fn(gen_structures)
        dm = cdist(test_comp_fps, gen_comp_fps)
    return dm


def cdvae_cov_match_matrix(
    test_structures,
    gen_structures,
    composition_only=False,
    symmetric=False,
    verbose=False,
    cutoff=10.0,
):
    dm = cdvae_cov_dist_matrix(
        test_structures,
        gen_structures,
        composition_only=composition_only,
        symmetric=symmetric,
        verbose=verbose,
    )
    return dm <= cutoff


def cdvae_cov_compstruct_match_matrix(
    test_structures,
    gen_structures,
    symmetric=False,
    comp_cutoff=10.0,
    struct_cutoff=0.4,
    verbose=False,
):
    comp_match_matrix = cdvae_cov_match_matrix(
        test_structures,
        gen_structures,
        composition_only=True,
        symmetric=symmetric,
        verbose=verbose,
        cutoff=comp_cutoff,
    )
    struct_match_matrix = cdvae_cov_match_matrix(
        test_structures,
        gen_structures,
        composition_only=False,
        symmetric=symmetric,
        verbose=verbose,
        cutoff=struct_cutoff,
    )
    # multiply, since 0*0=0, 0*1=0, 1*0=0, 1*1=1
    return comp_match_matrix * struct_match_matrix


ALLOWED_MATCH_TYPES = ["StructureMatcher", "cdvae_coverage"]


def get_match_matrix(
    test_structures,
    gen_structures,
    match_type="cdvae_coverage",
    symmetric=False,
    verbose=False,
    **match_kwargs,
):
    assert (
        match_type in ALLOWED_MATCH_TYPES
    ), f"type must be one of {ALLOWED_MATCH_TYPES}"

    if match_type == "cdvae_coverage":
        return cdvae_cov_compstruct_match_matrix(
            test_structures,
            gen_structures,
            symmetric=symmetric,
            verbose=verbose,
            **match_kwargs,
        )
    elif match_type == "StructureMatcher":
        return structure_pairwise_match_matrix(
            test_structures,
            gen_structures,
            match_type="StructureMatcher",
            symmetric=symmetric,
            verbose=verbose,
            **match_kwargs,
        )


# %% Code Graveyard

# if verbose:
#     logger.info("Decorating structures with oxidation states")
# oxi_structures = []
# for s in structures:
#     try:
#         oxi_struct = bva.get_oxi_state_decorated_structure(s)
#     except ValueError:
#         # TODO: track how many couldn't have valences assigned
#         oxi_struct = s
#     oxi_structures.append(oxi_struct)
