from itertools import product

from demos.auction_model import demo


def test02():
    sellers = [4]
    buyers = [100]
    results = demo(sellers, buyers, time_limit=False)
    expected_results = {100: 4, 4: 100}
    for k, v in results.items():
        assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k, v)


def test03():
    expected_results = {101: 5, 5: 101, 6: None, 7: None}
    sellers = [k for k in expected_results if k < 100]
    buyers = [k for k in expected_results if k >= 100]
    results = demo(sellers, buyers)
    for k, v in results.items():
        assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k, v)


def test04():
    expected_results = {0: 101, 101: 0, 102: None,
                        103: None}  # result: 0 enters contract with price 334.97 (the highest price)
    sellers = [k for k in expected_results if k < 100]
    buyers = [k for k in expected_results if k >= 100]
    results = demo(sellers, buyers)
    for k, v in results.items():
        assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k, v)


def test05():
    expected_results = {101: 7, 102: 6, 103: 5, 5: 103, 6: 102, 7: 101}
    sellers = [k for k in expected_results if k < 100]
    buyers = [k for k in expected_results if k >= 100]
    results = demo(sellers, buyers)
    for k, v in results.items():
        assert expected_results[k] == v, "Hmmm... That's not right {}={}".format(k, v)


def test06():
    expected_results = {0: 102, 1: 108, 2: 105, 3: 107, 4: 100, 5: 106, 6: 112, 7: 111, 8: 103, 9: 109, 10: 104, 100: 4, 101: None, 102: 0, 103: 8, 104: 10, 105: 2, 106: 5, 107: 3, 108: 1, 109: 9, 110: None, 111: 7, 112: 6}
    sellers = [k for k in expected_results if k < 100]
    buyers = [k for k in expected_results if k >= 100]
    error_sets = []

    for s_init, b_init in list(product([True, False], repeat=2)):
        if not s_init and not b_init:
            continue  # if neither seller or buyer initialise, obviously nothing will happen.
        results = demo(sellers=sellers, buyers=buyers, seller_can_initialise=s_init, buyer_can_initialise=b_init)
        errors = []
        for k, v in results.items():
            if not expected_results[k] == v:  # , "Hmmm... That's not right {}={}".format(k, v)
                errors.append((k, v))
        if errors:
            error_sets.append(errors)
    if error_sets:
        print("-" * 80)
        for i in error_sets:
            print(",".join(str(i) for i in sorted(i)), flush=True)
        raise AssertionError("output does not reflect expected results.")