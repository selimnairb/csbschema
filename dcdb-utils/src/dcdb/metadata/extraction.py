from datetime import datetime, timezone, timedelta


def sort_dict_list_by_keys(input: list, output: list) -> list:
    for e in input:
        if isinstance(e, dict):
            d = {}
            output.append(d)
            sort_dict_by_keys(e, d)
        elif isinstance(e, list):
            l = []
            output.append(l)
            sort_dict_list_by_keys(e, l)
        else:
            output.append(e)

def sort_dict_by_keys(input: dict, output: dict, *,
                      exclude_keys: tuple = ('time', 'fileType', 'submissionInfo', 'dataProcessed')) -> dict:
    for k, v in sorted(input.items()):
        if k in exclude_keys:
            continue
        if isinstance(v, dict):
            output[k] = {}
            sort_dict_by_keys(v, output[k],
                              exclude_keys=exclude_keys)
        elif isinstance(v, list):
            output[k] = []
            sort_dict_list_by_keys(v, output[k])
        else:
            output[k] = v
    return output

def get_unique_vessel_id(data: dict) -> str|None:
    if 'platform' in data:
        platform = data['platform']
        if 'uniqueID' in platform:
            uniqueId = platform['uniqueID']
            if not isinstance(uniqueId, str):
                raise ValueError(f"Expected uniqueID to be of type str but is of type {type(uniqueId)}")
            return uniqueId
    if 'trustedNode' in data:
        trustedNode = data['trustedNode']
        if 'uniqueVesselID' in trustedNode:
            uniqueVesselId = trustedNode['uniqueVesselID']
            if not isinstance(uniqueVesselId, str):
                raise ValueError(f"Expected uniqueVesselId to be of type str but is of type {type(uniqueVesselId)}")
            return uniqueVesselId
    return None

def get_start_end_times(data: dict) -> tuple[int, int]|tuple[None, None]:
    if 'time' in data:
        time_block = data['time']
        if 'startTime' not in time_block or 'endTime' not in time_block:
            return None, None
        try:
            start_time = time_block['startTime']
        except ValueError:
            return None, None
        try:
            end_time = time_block['endTime']
        except ValueError:
            return None, None
        return start_time, end_time
    return None, None
