l = 10
area = 100
parameters = {
    "results": [
        {
            "type": "tabular",
            "identifier": [
                {   "label": "x1",
                    "symbol": "U2",
                    "nset": "LOADAPP"
                },
                {   "label": "x2",
                    "symbol": "U2",
                    "position": "Node 4",
                    "nset": "LOADFOLLOWERS"
                },
                {   "label": "y",
                    "symbol": "RF2",
                    "nset": "LOADAPP"
                }
            ],
            # Use eval statements to calculate a reference strain and stress val from abaqus output of force and disp
            "xEvalStatement": "(d['x1'] + d['x2']) / (2 * {l})".format(l=l),
            "yEvalStatement": "d['y']/ {area}".format(area=area),
            "referenceValue": [
                            (0.0, 0.0), 
                            (0.000582908, 1.49516), 
                            (0.000944326, 2.4222), 
                            (0.00138836, 3.56113)
                            ],
            "tolerance": (0.0001, 0.350)
        }
    ]
}
