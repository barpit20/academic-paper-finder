import inspect
import re
import os
import sys
import progressbar

def search_for(obj, look_in, look_for):
    string = obj[look_in]
    return string.find(look_for.replace('*', '')) > -1

def insert_identifier(string, identifier, replace = 'identifier'):
    return string.replace("{%s}" % str(replace), str(identifier))

def get_dict_field(d, field, default=None):
    def throw(): 
        if default is None:
            raise ValueError("%s could not be found in dict", field)
        else:
            return default
    
    if not isinstance(d, dict) and not isinstance(d, list):
        raise Exception(f"Should not try to access other than dicts and lists: {type(d)}")
    
    i = field.find(".")
    if i > -1:
        key = field[0:i]
        if key == '*' and isinstance(d, list):
            res = []
            for value in d:
                res.append(get_dict_field(value, field[i+1:]))
            return res
        elif isinstance(d, list):
            try:
                index = int(key)
                return get_dict_field(d[index], field[i+1:])
            except:
                return throw()
        if key not in d: return throw()
        return get_dict_field(d[key], field[i+1:])
    
    if field not in d: return throw()
    return d[field]

def check_file_exists(file_path):
    return os.path.exists(file_path)

def strip_html(html):
    return re.sub(r'<[^<]+?>', '', html)

def safe_filename(filename):
    return re.sub(r'[^\.\w\d-]','_',filename)

def ensure_path_exists(file_path, is_directory=False):
    if is_directory:
        directory = file_path
    else:
        directory = os.path.dirname(file_path)
    try:
        os.stat(directory)
    except:
        os.makedirs(directory)

def unique(l): 
    unique_list = [] 
    for x in l: 
        if x not in unique_list: 
            unique_list.append(x) 
    return unique_list

def flatten(l):
    if not any(isinstance(el, list) for el in l): return l
    return [item for sublist in l for item in sublist]

def console_up():
    # My terminal breaks if we don't flush after the escape-code
    sys.stdout.write('\x1b[1A')
    sys.stdout.flush()

def console_down():
    # I could use '\x1b[1B' here, but newline is faster and easier
    sys.stdout.write('\n')
    sys.stdout.flush()

def get_progressbar(maxval, obj='papers'):
    widgets=[
        f'Fetching {obj}: ', 
        ' [', progressbar.Timer(), '] ',
        progressbar.Bar(),
        ' (', progressbar.ETA(), ') ',
    ]
    return progressbar.ProgressBar(maxval=maxval, widgets=widgets)

def file_name_from_url(url, content_disposition=None, file_ext='.pdf'):
    default = url.rsplit('/', 1)[1]
    if not default.endswith(file_ext): default = default + file_ext
    if not content_disposition: return default
    fname = re.findall('filename=(.+)', content_disposition)
    if len(fname) == 0: return default
    return fname[0]

class ShouldBeImplementedInSubclassError(Exception):
    """Exception raised for errors in the input.

    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self):
        self.expression = inspect.stack()[1][3]
        self.message = "needs to be implemented in subclass"