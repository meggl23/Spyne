from .Utility import *
from skimage.feature import canny
from skimage.registration import phase_cross_correlation

import json

from .Spine import Synapse


def SpineShift(tiff_Arr_small):

    """
    Input:
            tiff_Arr_small (np.array of doubles)  : Pixel values of local area surrounding a spine
    Output:
            SpineMinDir (list of ints)            : Local shifting so ROI follows spine

    Function:
           Using the phase cross correlation algorithm we can work out how to shift the ROIs
    """
    MinDir2 = np.zeros([2, tiff_Arr_small.shape[0] - 1])
    for t in range(tiff_Arr_small.shape[0] - 1):
        shift, _, _ = phase_cross_correlation(
            tiff_Arr_small[t, :, :], tiff_Arr_small[t + 1, :, :]
        )
        MinDir2[:, t] = -shift.astype(int)

    MinDirCum = np.cumsum(MinDir2, 1)
    MinDirCum = np.insert(MinDirCum, 0, 0, 1)

    return MinDirCum


def FindShape(
    tiff_Arr_m,
    pt,
    DendArr_m,
    other_pts,
    bg,
    ErrorCorrect=False,
    sigma=1.5,
    CheckVec=[True, True, True, True],
    tol=3,
):

    """
    Input:
            tiff_Arr (np.array of doubles)  : Pixel values of all the tiff files
            pt       ([int,int])            : Point of interest for roi
            DendArr_m (np.array of doubles) : Location of the dendritic branch
            other_pts (np.array of ints)    : Locations of other rois
            bg (double)                     : value of background
            ErrorCorrect (bool)             : Flag to see if perturbations of pt
                                              should also be analysed
            sigma (double)                  : Value of canny image variance
            CheckVec (list of bools)        : Which of the conditions we impose
            tol (int)                       : How many strikes we accept before stopping
    Output:
            xprt (np.array of ints)         : shape of roi
            SpineMinDir (list of ints)      : Local shifting so ROI follows spine
            OppDir (np.array of ints)       : Vector pointing away from dendrite

    Function:
            Using a set of rules based on the luminosity we aim to encircle the spine
            and pass this out via xpert. Current rules are, "Sanity check", "Fall-off"
            "Dendrite criterion", "Overlap criterion" and "Fallback criterion"
    """
    SpineMinDir = None
    if tiff_Arr_m.ndim > 2:
        tiff_Arr = tiff_Arr_m.max(axis=0)
        if ErrorCorrect:
            tiff_Arr_small = tiff_Arr_m[
                :,
                max(pt[1] - 50, 0) : min(pt[1] + 50, tiff_Arr_m.shape[-2]),
                max(pt[0] - 50, 0) : min(pt[0] + 50, tiff_Arr_m.shape[-1]),
            ]
            SpineMinDir = SpineShift(tiff_Arr_small).T.astype(int).tolist()
            tiff_Arr = np.array(
                [
                    np.roll(tiff_Arr_m, -np.array(m), axis=(-2, -1))[i, :, :]
                    for i, m in enumerate(SpineMinDir)
                ]
            ).max(axis=0)
    else:
        tiff_Arr = tiff_Arr_m

    cArr = canny(tiff_Arr, sigma=sigma)

    strikes = 0
    Directions = {
        "N": [0, 1, True, "S", 0, strikes, True],
        "NW": [-1, 1, True, "SE", 0, strikes, True],
        "W": [-1, 0, True, "E", 0, strikes, True],
        "SW": [-1, -1, True, "NE", 0, strikes, True],
        "S": [0, -1, True, "N", 0, strikes, True],
        "SE": [1, -1, True, "NW", 0, strikes, True],
        "E": [1, 0, True, "W", 0, strikes, True],
        "NE": [1, 1, True, "SW", 0, strikes, True],
    }

    xpert = np.array([pt, pt, pt, pt, pt, pt, pt, pt])
    maxval = tiff_Arr[pt[1], pt[0]]

    Closest = 0
    if CheckVec[2]:
        if len(DendArr_m) > 1:
            Closest = [np.min(np.linalg.norm(pt - d, axis=1)) for d in DendArr_m]
            DendArr = DendArr_m[np.argmin(Closest)]
            Closest = np.argmin(Closest)
        else:
            DendArr = DendArr_m[0]
        Order0 = np.sort(
            np.argsort(np.linalg.norm(np.asarray(DendArr) - np.asarray(pt), axis=1))[
                0:2
            ]
        )

        pt_proc = np.array(projection(DendArr[Order0[0]], DendArr[Order0[1]], pt))
        OppDir = np.array(3 * pt - 2 * pt_proc).astype(int)
        OppDir[0] = max(min(OppDir[0], tiff_Arr.shape[-1] - 10), 10)
        OppDir[1] = max(min(OppDir[1], tiff_Arr.shape[-2] - 10), 10)
    else:
        OppDir = pt
    o_arr = np.asarray(other_pts)

    if CheckVec[3]:
        for keys in Directions.keys():
            for x, y in zip(DendArr[:-1, :], DendArr[1:, :]):
                lam, mu = crosslen(x, y, pt, pt + Directions[keys][:2])
                if (mu < 0) or (lam > 1 or lam < 0):
                    Directions[keys][-1] = True
                else:
                    Directions[keys][-1] = False
                    break

    while any([x[2] for x in Directions.values()]):
        for j, keys in enumerate(Directions.keys()):
            if Directions[keys][2]:
                maxval = max(maxval, tiff_Arr[xpert[j][1], xpert[j][0]])
                xpert[j] = xpert[j] + Directions[keys][:2]
                Directions[keys][4] = np.linalg.norm(pt - xpert[j])

                # Sanity check
                if (
                    xpert[j] > [tiff_Arr.shape[1] - 1, tiff_Arr.shape[0] - 1]
                ).any() or (xpert[j] < 1).any():
                    Directions[keys][-2] += 3
                    Directions[keys][2] = False
                    break

                # Contour check
                if cArr[xpert[j][1], xpert[j][0]] == True and CheckVec[0]:
                    if Directions[keys][4] <= 4:
                        if Directions[keys][4] > 1:
                            Directions[keys][-2] += 1
                    elif Directions[keys][4] <= 8:
                        Directions[keys][-2] += 2
                    else:
                        Directions[keys][-2] += 3

                # Fall off criterion
                if (
                    tiff_Arr[xpert[j][1], xpert[j][0]] < 4 * bg
                    or 3 * tiff_Arr[xpert[j][1], xpert[j][0]] < maxval
                ) and CheckVec[1]:
                    if Directions[keys][4] <= 4:
                        if Directions[keys][4] > 1:
                            Directions[keys][-2] += 1
                    elif Directions[keys][4] <= 8:
                        Directions[keys][-2] += 2
                    else:
                        Directions[keys][-2] += 3

                # Dendrite criterion
                if CheckVec[2]:
                    if (
                        np.linalg.norm(pt - xpert[j])
                        > np.linalg.norm(pt_proc - xpert[j])
                        and np.linalg.norm(pt_proc - pt) > 5
                    ):
                        Directions[keys][-2] += 3

                # Increasing criterion
                if (
                    not Directions[keys][-1]
                    and Directions[keys][4] > 5
                    and tiff_Arr[xpert[j][1], xpert[j][0]] > 1.5 * maxval
                ) and CheckVec[3]:
                    Directions[keys][-2] += 1

                # Overlap criterion
                if not o_arr.size == 0:
                    if np.any(
                        np.linalg.norm(xpert[j] - o_arr, axis=1)
                        < np.linalg.norm(xpert[j] - pt)
                    ):
                        Directions[keys][-2] += 3

                # Fallback criterion
                if (
                    not Directions[Directions[keys][3]][2]
                    and Directions[keys][4] > 2 * Directions[Directions[keys][3]][4]
                ):
                    Directions[keys][-2] += 1

                if Directions[keys][-2] >= tol:
                    Directions[keys][2] = False

    if ErrorCorrect:
        o_arr2 = np.delete(o_arr, np.where(np.all(o_arr == pt, axis=1)), axis=0)
        xpert1, _, _,_ = FindShape(
            tiff_Arr, pt + [0, 1], DendArr_m, o_arr2, bg, False, sigma, CheckVec, tol
        )
        xpert2, _, _,_ = FindShape(
            tiff_Arr, pt + [0, -1], DendArr_m, o_arr2, bg, False, sigma, CheckVec, tol
        )
        xpert3, _, _,_ = FindShape(
            tiff_Arr, pt + [1, 0], DendArr_m, o_arr2, bg, False, sigma, CheckVec, tol
        )
        xpert4, _, _,_ = FindShape(
            tiff_Arr, pt + [-1, 0], DendArr_m, o_arr2, bg, False, sigma, CheckVec, tol
        )
        xpert = np.stack((xpert, xpert1, xpert2, xpert3, xpert4)).mean(0)
        xpert = xpert.tolist()
    return xpert, SpineMinDir, OppDir,Closest


def SynDistance(SynArr, DendArr_m, Unit):

    """
    Input:
            SynArr  (list of synapses)
            DendArr_m (list of np.array of doubles) : Location of the dendritic branches
            Unit                                    : The size of each pixel
            Mode (String)                           : Type of data we are collecting
    Output:
            SynArr  (list of synapses)

    Function:
            Find the distance of either the soma or the closest stimulated spine.
            Also, depending on whether the spine is inside or outside the cluster
            the distance will be negative or positive, respectively
    """
    for S in SynArr:
        DendArr = DendArr_m[S.closest_Dend]
        S.distance = SynDendDistance(S.location, DendArr, DendArr[0]) * Unit
    return SynArr

def SynDendDistance(loc, DendArr, loc0):

    """
    Input:
            loc       ([int,int])         : Point of interest of spine
            DendArr (np.array of doubles) : Location of the dendritic branch
            loc0       ([int,int])         : Point of interest of closest stim
    Output:
            Distance (real)

    Function:
            Find the distance of closest stim and chosen spines
    """

    DoneDist = [np.linalg.norm(d1 - d2) for d1, d2 in zip(DendArr[:-1], DendArr[1:])]
    Order0 = np.sort(
        np.argsort(np.linalg.norm(np.asarray(DendArr) - np.asarray(loc0), axis=1))[0:2]
    )
    S0Proc = projection(DendArr[Order0[0]], DendArr[Order0[1]], loc0)
    S0Dist = np.linalg.norm(np.asarray(DendArr)[Order0] - S0Proc, axis=1)

    Order = np.sort(
        np.argsort(np.linalg.norm(np.asarray(DendArr) - np.asarray(loc), axis=1))[0:2]
    )
    SProc = projection(DendArr[Order[0]], DendArr[Order[1]], loc)
    Distance = 0
    if ((Order0 == Order)).all():
        Distance = np.linalg.norm(np.array(SProc) - np.array(S0Proc))
    elif Order0[0] >= Order[1]:
        Distance = np.linalg.norm(SProc - DendArr[Order[1]])
        for i in range(Order[1], Order0[0]):
            Distance += DoneDist[i]
        Distance += S0Dist[0]
    elif Order0[1] <= Order[0]:
        Distance = np.linalg.norm(SProc - DendArr[Order[0]])
        for i in range(Order[0], Order0[1], -1):
            Distance += DoneDist[i - 1]
        Distance += S0Dist[1]
    else:
        Distance = np.linalg.norm(np.array(SProc) - np.array(S0Proc))

    return Distance

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        return json.JSONEncoder.default(self, obj)


def SaveSynDict(SynArr, Dir, Mode):

    """
    Input:
            SynArr  (list of synapses)
            bg (list of doubles)         : Background values of the snapshots
            Dir (String)                 : Super directory we are looking at
            Mode (String)                : Type of data we are collecting
    Output:
            N/A

    Function:
            Save list of spines as json file
    """

    for S in SynArr:
        try:
            S.points = [arr.tolist() for arr in S.points]
        except:
            pass
        try:
            S.radloc = S.radloc.tolist()
        except:
            pass
    if Mode == "Area":
        with open(Dir + "Synapse_a.json", "w") as fp:
            json.dump([vars(S) for S in SynArr], fp, indent=4,cls=NumpyEncoder)
    elif Mode == "Luminosity":
        with open(Dir + "Synapse_l.json", "w") as fp:
            json.dump([vars(S) for S in SynArr], fp, indent=4,cls=NumpyEncoder)
    else:
        with open(Dir + "Synapse.json", "w") as fp:
            json.dump([vars(S) for S in SynArr], fp, indent=4,cls=NumpyEncoder)

    return 0


def ReadSynDict(Dir, nSnaps, unit, Mode):

    """
    Input:
            Dir (String)   : Super directory we are looking at
            nSnaps (int)   : Number of snapshots
            Unit (double)  : The size of each pixel
            Mode (String)  : Type of data we are collecting
    Output:
            SynArr  (list of synapses)
    Function:
            Read Json file to obtain saved list of synapses
    """
    if(Mode=="Area"):
        FileName="Synapse_a.json"
        FileName2="Synapse_l.json"
    else:
        FileName="Synapse_l.json"
        FileName2="Synapse_a.json"

    try:
        with open(Dir + FileName, "r") as fp:
            temp = json.load(fp)
    except:
        with open(Dir + FileName2, "r") as fp:
            temp = json.load(fp)

    SynArr = []

    for t in temp:
        try:
            SynArr.append(
                Synapse(
                    t["location"],
                    t["radloc"],
                    nSnaps=nSnaps,
                    stack=0,
                    Unit=unit,
                    Syntype=t["type"],
                    dist=t["distance"],
                    xpert=t["xpert"],
                    shift=t["shift"],
                )
            )
        except:
            try:
                SynArr.append(
                    Synapse(
                        t["location"],
                        t["bgloc"],
                        Syntype=t["type"],
                        dist=t["distance"],
                        pts=t["points"],
                        shift=t["shift"],
                        channel=t["channel"],
                        local_bg=t["local_bg"],
                        closest_Dend=t["closest_Dend"]
                    )
                )
            except:
                SynArr.append(
                    Synapse(
                        t["location"],
                        t["bgloc"],
                        Syntype=t["type"],
                        dist=t["distance"],
                        pts=t["points"],
                        shift=t["shift"],
                        channel=t["channel"],
                        local_bg=t["local_bg"],
                        closest_Dend=t["closest_Dend"]
                    )
                )
                SynArr[-1].shift = np.zeros([9, 2]).tolist()

    return SynArr