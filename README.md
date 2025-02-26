# Fairness-Enhancing Classification Methods For Non-Binary Sensitive Features - How to Fairly Detect Leakages in Water Distribution Networks
This repository contains the implementation of the methods proposed in the paper ["Fairness-Enhancing Classification Methods For Non-Binary Sensitive Features - How to Fairly Detect Leakages in Water Distribution Networks"](Paper.pdf) by Janine Strotherm, Inaam Ashraf and Barbara Hammer.
This paper is an extended version of the paper ["Fairness-Enhancing Ensemble Classification in Water Distribution Networks"](https://github.com/jstrotherm/FairnessInWDNs/blob/main/Paper.pdf) by Janine Strotherm and Barbara Hammer.

## Abstract
Especially if AI-supported decisions affect the society, the fairness of such AI-based methodologies constitutes an important area of research. In this contribution, we investigate the applications of AI to the socioeconomically relevant infrastructure of water distribution systems (WDSs). We propose an appropriate definition of protected groups in WDSs and generalized definitions of group fairness that provably coincide with existing definitions in their specific settings. We demonstrate that typical methods for the detection of leakages in WDSs are unfair in this sense. Further, we thus propose a general fairness-enhancing framework as an extension of the specific leakage detection pipeline, but also for an arbitrary learning scheme, to increase the fairness of the AI-based algorithm. Finally, we evaluate and compare several specific instantiations of this framework on a toy and on a realistic WDS to show their utility.

## Details
The implementation of the proposed methods can be found in the `Implementation` folder. 

The data required for these methods are stored or can be generated using the `2_DataGeneration` subfolder:
-   The subfolder `2_DataGeneration/Hanoi` holds the data associated with the Hanoi network stored as excel files.
    It is the same data as used in [this previous work](https://github.com/jstrotherm/FairnessInWDNs/blob/main/Paper.pdf). 
    For the data generation, we refer to [this previous repository](https://github.com/jstrotherm/FairnessInWDNs). 
    In this repository, we only store the resulting excel files.
-   The subfolder `2_DataGeneration/L-Town` is a modified version of [this previous repository](https://github.com/HammerLabML/GCNs_for_WDS). 
    - Due to their sizes, some of additionally required files can not be stored in this repository. 
    Therefore, it is required to 
    a) download [this .inp file](https://github.com/KIOS-Research/BattLeDIM/blob/master/Dataset%20Generator/L-TOWN_v2_Real.inp) and store it as `2_DataGeneration/L-Town/networks/L-Town/Real/L-TOWN_Real.inp` and 
    b) train a model as specified in [this previous repository](https://github.com/HammerLabML/GCNs_for_WDS) and store it as `2_DataGeneration/L-Town/trained_models/model_L-TOWN_2880_45_1.pt`. 
    - Afterwards, 
    running the `gen_scenario_leakages.py` script generates different leakage scenarios. 
    - Consecutively, 
    running the `get_scenario_residuals.py` script generates the data associated with the L-Town network and stores it in a csv file. 
    - Finally, 
    running the `get_node_ids.ipynb` notebook generates network information required for the network visualization and stores it in a csv file.
    - The csv files are not stored in this repository due to their sizes. 
-   The excel and csv files are in turn used in the `3_DataUsage` subfolder.

The methods themselves can be used using the `3_DataUsage` subfolder:
-   In the `FairnessExploration_Hanoi_extended.ipynb` and in the `FairnessExploration_L-Town.ipynb` notebook, the proposed approaches and results are implemented.

## Requirements
All requirements for the whole project are listed in the `Implementation/requirements.txt` file.

## How To Cite
You can cite the corresponding paper using the following BibTex entry:
```
@article{
    Strotherm2024FairClassification,
    author      = {Strotherm, Janine and Ashraf, Inaam and Hammer, Barbara},
    title       = {{Fairness-enhancing classification methods for non-binary sensitive features -- How to fairly detect leakages in water distribution systems}},
    year        = {2024},
    journal     = {PeerJ Computer Science},
    publisher   = {PeerJ},
    volume      = {10},
    pages       = {e2317}
}
```
