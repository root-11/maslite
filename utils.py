from datetime import datetime, timedelta

epoch = datetime(1970, 1, 1)
time_fmt = "%Y-%m-%dT%H:%M:%S"


def object_printer(obj, add_footer=30, skip=[], time=[]):
    """estring is the expose function repacked for utils.
    :param: obj: is the object from self.
    :param: add_footer: integer, adds a footer.
    :param: skip: does not output attribute names from this list/set
    :returns: str
    """

    attrname_width = max([len(str(attr)) for attr in dir(obj)])

    s = ["%s\n" % type(obj).__name__]
    for attribute in sorted(dir(obj)):
        if attribute.startswith("_"):
            continue
        elif callable(getattr(obj, attribute)):
            continue
        elif attribute in skip:
            continue
        else:
            txt = "{}".format(attribute)
            txt = txt.ljust(attrname_width)
            if attribute in time:
                val = getattr(obj, attribute)
                if val is not None:
                    val = datetime_from_seconds(val).strftime("%Y-%m-%d %H:%M:%S")
            else:
                val = ("{}".format(getattr(obj, attribute)))
            s.append("{} | {}\n".format(txt, val))
    if add_footer:
        # +2 for " |" column separator
        footer = "-" * (attrname_width+2+add_footer) + '\n'
        s.append(footer)
        s.insert(1, footer)
        s.insert(0, footer)
        s.insert(0, '\n')
    return "".join(s)

def datetime_from_seconds(floating_point_value):
    """converts to datetime object from seconds
    :param: seconds as floating point
    :returns: datetime object
    """
    delta = timedelta(0, floating_point_value)
    dt_obj = epoch + delta
    return dt_obj