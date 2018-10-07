parameters = {
    "results": [
        {
            "type": "min",
            "identifier":
                {
                    "label": "s11",
                    "symbol": "S11",
                    "elset": "ALL",
                    "position": "Element 1 Int Point 1"
                },
            "evalStatement": "d['s11'] - 1",
            "referenceValue": -17101.0,
            "tolerance": 1.0
        },
        {
            "type": "max",
            "identifier":
                {
                    "label": "s22",
                    "symbol": "S22",
                    "elset": "ALL",
                    "position": "Element 1 Int Point 1"
                },
            "evalStatement": "d['s22'] + 1",
            "referenceValue": 1,
            "tolerance": 0.1
        }
    ]
}
