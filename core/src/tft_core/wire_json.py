"""Exact integer transport for JavaScript evidence viewers.

Offline EvidenceGraph values stay unchanged. Paged wire copies use decimal
strings for integers outside JavaScript's safe range and identify those values
with paths relative to the response document, distinct from evidence paths.
"""


def evidence_wire_page(page):
    integer_paths=[]
    def visit(value,path):
        if type(value) is int and abs(value)>2**53-1:
            integer_paths.append(path)
            return str(value)
        if isinstance(value,list):
            return [visit(item,path+[index]) for index,item in enumerate(value)]
        if isinstance(value,dict):
            return {key:visit(item,path+[key]) for key,item in value.items()}
        return value
    if 'integer_paths' in page:
        raise ValueError('Reserved evidence wire metadata')
    result=visit(page,[])
    result['integer_paths']=integer_paths
    return result
