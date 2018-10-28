import os
import json
import utils
import glob
import random
from tqdm import tqdm
from shutil import copyfile

from execution import Relation, State
from scripts import read_script, read_script_from_string, read_script_from_list_string, ScriptParseException
from execution import ScriptExecutor
from environment import EnvironmentGraph, Room
import ipdb


random.seed(123)
verbose = False
dump = False
max_nodes = 300


def dump_one_data(txt_file, script, graph_state_list, id_mapping):

    new_path = txt_file.replace('withoutconds', 'executable_programs')
    new_dir = os.path.dirname(new_path)
    if not os.path.exists(new_dir):
        os.makedirs(new_dir)

    # read old program
    old_f = open(txt_file, 'r')
    old_program = old_f.read()
    old_f.close()

    new_f = open(new_path, 'w')
    
    prefix = old_program.split('\n\n\n')[0]
    new_f.write(prefix)
    new_f.write('\n\n\n')

    for script_line in script:
        script_line_str = '[{}]'.format(script_line.action.name)
        if script_line.object():
            script_line_str += ' <{}> ({})'.format(script_line.object().name, script_line.object().instance)
        if script_line.subject():
            script_line_str += ' <{}> ({})'.format(script_line.subject().name, script_line.subject().instance)

        for k, v in id_mapping.items():
            obj_name, obj_number = k
            id = v
            script_line_str = script_line_str.replace('<{}> ({})'.format(obj_name, id), '<{}> ({}.{})'.format(obj_name, obj_number, id))
        
        new_f.write(script_line_str)
        new_f.write('\n')

    new_path = txt_file.replace('withoutconds', 'init_and_final_graphs').replace('txt', 'json')
    new_dir = os.path.dirname(new_path)
    if not os.path.exists(new_dir):
        os.makedirs(new_dir)

    new_f = open(new_path, 'w')
    #json.dump({"graph_state_list": graph_state_list}, new_f)
    json.dump({"init_graph": graph_state_list[0], "final_graph": graph_state_list[-1]}, new_f)
    new_f.close()


def translate_graph_dict(path):

    graph_dict = utils.load_graph_dict(path)
    properties_data = utils.load_properties_data(file_name='resources/object_script_properties_data.json')
    node_list = [node["class_name"] for node in graph_dict['nodes']]

    static_objects = ['bathroom', 'floor', 'wall', 'ceiling', 'rug', 'curtains', 'ceiling_lamp', 'wall_lamp', 
                        'bathroom_counter', 'bathtub', 'towel_rack', 'wall_shelf', 'stall', 'bathroom_cabinet', 
                        'toilet', 'shelf', 'door', 'doorjamb', 'window', 'lightswitch', 'bedroom', 'table_lamp', 
                        'chair', 'bookshelf', 'nightstand', 'bed', 'closet', 'coatrack', 'coffee_table', 
                        'pillow', 'hanger', 'character', 'kitchen', 'maindoor', 'tv_stand', 'kitchen_table', 
                        'bench', 'kitchen_counter', 'sink', 'power_socket', 'tv', 'clock', 'wall_phone', 
                        'cutting_board', 'stove', 'oventray', 'toaster', 'fridge', 'coffeemaker', 'microwave', 
                        'livingroom', 'sofa', 'coffee_table', 'desk', 'cabinet', 'standing_mirror', 'globe', 
                        'mouse', 'mousemat', 'cpu_screen', 'cpu_case', 'keyboard', 'ceilingfan', 
                        'kitchen_cabinets', 'dishwasher', 'cookingpot', 'wallpictureframe', 'vase', 'knifeblock', 
                        'stovefan', 'orchid', 'long_board', 'garbage_can', 'photoframe', 'balance_ball', 'closet_drawer']

    new_nodes = [i for i in filter(lambda v: v["class_name"] in static_objects, graph_dict['nodes'])]
    trimmed_nodes = [i for i in filter(lambda v: v["class_name"] not in static_objects, graph_dict['nodes'])]

    available_id = [i["id"] for i in filter(lambda v: v["class_name"] in static_objects, graph_dict['nodes'])]

    new_edges = [i for i in filter(lambda v: v['to_id'] in available_id and v['from_id'] in available_id, graph_dict['edges'])]

    # change the object name 
    script_object2unity_object = utils.load_name_equivalence()
    unity_object2script_object = {}
    for k, vs in script_object2unity_object.items():
        unity_object2script_object[k] = k
        for v in vs:
            unity_object2script_object[v] = k

    new_nodes_script_object = []
    for node in new_nodes:
        class_name = unity_object2script_object[node["class_name"]].lower().replace(' ', '_') if node["class_name"] in unity_object2script_object else node["class_name"].lower().replace(' ', '_')
        
        new_nodes_script_object.append({
            "properties": [i.name for i in properties_data[class_name]] if class_name in properties_data else node["properties"], 
            "id": node["id"], 
            "states": node["states"], 
            "category": node["category"], 
            "class_name": class_name
        })
    
    translated_path = path.replace('TestScene', 'TrimmedTestScene')
    json.dump({"nodes": new_nodes_script_object, "edges": new_edges, "trimmed_nodes": trimmed_nodes}, open(translated_path, 'w'))
    return translated_path


def check_script(program_str, precond, graph_path, inp_graph_dict=None, id_mapping={}, info={}):

    properties_data = utils.load_properties_data(file_name='../resources/object_script_properties_data.json')
    object_states = json.load(open('../resources/object_states.json'))
    object_placing = json.load(open('../resources/object_script_placing.json'))

    helper = utils.graph_dict_helper(properties_data, object_placing, object_states, max_nodes)

    #helper.initialize()
    try:
        script = read_script_from_list_string(program_str)
    except ScriptParseException:
        # print("Can not parse the script")
        return None, None, None, None, None
    
    if inp_graph_dict is None:
        graph_dict = utils.load_graph_dict(graph_path)
    else:
        graph_dict = inp_graph_dict
    message, executable, final_state, graph_state_list, id_mapping, info = check_one_program(
        helper, script, precond, graph_dict, w_graph_list=False, modify_graph=(inp_graph_dict is None), id_mapping=id_mapping, **info)

    return message, final_state, graph_dict, id_mapping, info


def check_one_program(helper, script, precond, graph_dict, w_graph_list, modify_graph=True, id_mapping={}, **info):

    for p in precond:
        for k, vs in p.items():
            if isinstance(vs[0], list): 
                for v in vs:
                    v[0] = v[0].lower().replace(' ', '_')
            else:
                v = vs
                v[0] = v[0].lower().replace(' ', '_')

    helper.initialize(graph_dict)
    if modify_graph:
        ## add missing object from scripts (id from 1000) and set them to default setting
        ## id mapping can specify the objects that already specify in the graphs
        id_mapping, first_room, room_mapping = helper.add_missing_object_from_script(script, precond, graph_dict, id_mapping)
        info = {'room_mapping': room_mapping}
        objects_id_in_script = [v for v in id_mapping.values()]
        helper.set_to_default_state(graph_dict, first_room, id_checker=lambda v: v in objects_id_in_script)

        ## place the random objects (id from 2000)
        helper.add_random_objs_graph_dict(graph_dict, n=max_nodes - len(graph_dict["nodes"]))
        helper.random_change_object_state(id_mapping, graph_dict, id_checker=lambda v: v not in objects_id_in_script)

        ## set relation and state from precondition
        helper.prepare_from_precondition(precond, id_mapping, graph_dict)
        helper.open_all_doors(graph_dict)
        #assert len(graph_dict["nodes"]) == max_nodes
    
    elif len(id_mapping) != 0:
        # Assume that object mapping specify all the objects in the scripts
        helper.modify_script_with_specified_id(script, id_mapping, **info)

    graph = EnvironmentGraph(graph_dict)

    name_equivalence = utils.load_name_equivalence()
    executor = ScriptExecutor(graph, name_equivalence)
    executable, final_state, graph_state_list = executor.execute(script, w_graph_list=w_graph_list)

    if executable:
        message = '{}, Script is executable'.format(0)
    else:
        message = '{}, Script is not executable, since {}'.format(0, executor.info.get_error_string())

    return message, executable, final_state, graph_state_list, id_mapping, info


def check_whole_set(dir_path, graph_path):
    """Use precondition to modify the environment graphs
    """

    info = {}

    program_dir = os.path.join(dir_path, 'withoutconds')
    program_txt_files = glob.glob(os.path.join(program_dir, '*/*.txt'))
    properties_data = utils.load_properties_data(file_name='resources/object_script_properties_data.json')
    object_states = json.load(open('resources/object_states.json'))
    object_placing = json.load(open('resources/object_script_placing.json'))

    helper = utils.graph_dict_helper(properties_data, object_placing, object_states, max_nodes)
    executable_programs = 0
    not_parsable_programs = 0
    executable_program_length = []
    not_executable_program_length = []
    #program_txt_files = [os.path.join(program_dir, 'results_intentions_march-13-18/file784_2.txt')]

    iterators = enumerate(program_txt_files) if verbose else tqdm(enumerate(program_txt_files))
    for j, txt_file in iterators:

        try:
            script = read_script(txt_file)
        except ScriptParseException:
            not_parsable_programs += 1            
            continue

        precond_path = txt_file.replace('withoutconds', 'initstate').replace('txt', 'json')
        precond = json.load(open(precond_path))

        graph_dict = utils.load_graph_dict(graph_path)

        message, executable, final_state, graph_state_list, id_mapping, _ = check_one_program(helper, script, precond, graph_dict, w_graph_list=True)
        
        if executable:
            if dump:
                dump_one_data(txt_file, script, graph_state_list, id_mapping)
            executable_program_length.append(len(script))
            executable_programs += 1
            if verbose:
                print(message)
        else:
            not_executable_program_length.append(len(script))
            if verbose:
                print(message)

        info.update({txt_file: message})

    print("Total programs: {}, executable programs: {}".format(len(program_txt_files), executable_programs))
    print("{} programs can not be parsed".format(not_parsable_programs))

    executable_program_length = sum(executable_program_length) / len(executable_program_length)
    not_executable_program_length = sum(not_executable_program_length) / len(not_executable_program_length)
    print("Executable program average length: {:.2f}, not executable program average length: {:.2f}".format(executable_program_length, not_executable_program_length))
    json.dump(info, open("executable_info.json", 'w'))


def check_executability(string, graph_dict):

    able_to_be_parsed = False
    able_to_be_executed = False
    try:
        script = read_script_from_string(string)
        able_to_be_parsed = True
    except ScriptParseException:
        return able_to_be_parsed, able_to_be_executed, None

    graph = EnvironmentGraph(graph_dict)
    name_equivalence = utils.load_name_equivalence()
    executor = ScriptExecutor(graph, name_equivalence)
    executable, final_state, _ = executor.execute(script)
    
    if executable:
        able_to_be_executed = True
        return able_to_be_parsed, able_to_be_executed, final_state.to_dict()
    else:
        return able_to_be_parsed, able_to_be_executed, None


def modify_script(script):

    modif_script = []
    for script_line in script.split(', '):
        action, object_name, object_i, subject_name, subject_i = script_line.split(' ')
        if object_name in ['<<none>>', '<<eos>>']:
            modif_script.append(action)
        elif subject_name in ['<<none>>', '<<eos>>']:
            modif_script.append('{} {} {}'.format(action, object_name, object_i))
        else:
            modif_script.append('{} {} {} {} {}'.format(action, object_name, object_i, subject_name, subject_i))

    return ', '.join(modif_script)


def example_check_executability():

    script1 = '[watch] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>), [find] <food_sugar> (1) <<none>> (<none>)'
    script2 = '[find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>), [find] <light> (1) <<none>> (<none>)'
    
    graph_dict = json.load(open('example_graphs/TrimmedTestScene6_graph.json'))
    executability = check_executability(modify_script(script2), graph_dict)
    print("Script is {}executable".format('' if executability else 'not '))


if __name__ == '__main__':
    
    #translated_path = translate_graph_dict(path='example_graphs/TestScene6_graph.json')
    translated_path = 'example_graphs/TrimmedTestScene6_graph.json'
    #check_whole_set('dataset_augmentation/augmented_location_augmented_affordance_programs_processed_precond_nograb_morepreconds', graph_path=translated_path)
    #check_whole_set('dataset_augmentation/perturb_augmented_location_augmented_affordance_programs_processed_precond_nograb_morepreconds', graph_path=translated_path)
    check_whole_set('programs_processed_precond_nograb_morepreconds', graph_path=translated_path)
