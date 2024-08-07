import datetime, copy, os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import wntr
import torch
from torch_geometric.data import Dataset, InMemoryDataset, Data
import torch.nn.functional as F
import networkx as nx
from xlsx2csv import Xlsx2csv
from io import StringIO
from python_calamine import get_sheet_data


class WaterFutureScenario:
    """
    Object that loads the Waterfutures Scenario.
    ...    

    Methods
    -------
    
    get_demands():
        Return demands of the scenario.    
    get_pressures():
        Return pressures of the scenario.
    
    """

    def __init__(self, directory, leaks_path):
        
        """
        directory : str - directory of the measurements.            
        """
        
        self.__directory = directory
        self.__time_start = None
        self.__time_step_seconds = None
        self.__leaks_path = leaks_path
        self.__demands = None
        self.__pressures = None
        self.__leaks = None
        self.__leaks_details = None

    def __load_time_info(self):
        tmp_df = self.get_pressures()
        self.__time_start = tmp_df.index[0]
        time_step = tmp_df.index[1]
        self.__time_step_seconds = (time_step - self.__time_start).total_seconds()

    def __timestamp_to_idx(self, timestamp):
        if self.__time_start is None or self.__time_step_seconds is None:
            self.__load_time_info()
        
        date_format = '%Y-%m-%d %H:%M:%S'
        cur_time = datetime.datetime.strptime(timestamp, date_format)
        return int((cur_time - self.__time_start).total_seconds() / self.__time_step_seconds)

    def __load_demands(self):
        ''' Load the demands for this scenario and save in internal variable. '''
        path_to_demands = self.__directory

        try:
            tmp_df = pd.read_csv(path_to_demands)
        except:
            recs: list[list] = get_sheet_data(path_to_demands, sheet=1)
            tmp_df = pd.DataFrame.from_records(recs, coerce_float=True)
            tmp_df.columns = tmp_df.iloc[0]
            tmp_df = tmp_df.drop(tmp_df.index[0])
       
        tmp_df['Timestamp'] = pd.to_datetime(tmp_df['Timestamp'])
        self.__demands = tmp_df.set_index("Timestamp")
       
    def get_demands(self):
        if self.__demands is None:
            self.__load_demands()
        return self.__demands.copy()   

    def __load_pressures(self):
        path_to_pressures = self.__directory
        try:
            tmp_df = pd.read_csv(path_to_pressures)
        except:
            recs: list[list] = get_sheet_data(path_to_pressures, sheet=0)
            tmp_df = pd.DataFrame.from_records(recs, coerce_float=True)
            tmp_df.columns = tmp_df.iloc[0]
            tmp_df = tmp_df.drop(tmp_df.index[0])

        tmp_df['Timestamp'] = pd.to_datetime(tmp_df['Timestamp'])#, unit='s')
        self.__pressures = tmp_df.set_index("Timestamp")
    
    def get_pressures(self):
        if self.__pressures is None:
            self.__load_pressures()
        return self.__pressures.copy()
    
    def __load_leaks_details(self):
        if self.__leaks_path is None:
            self.__leaks_details =  pd.DataFrame.empty
            return

        file_leaks = self.__leaks_path 
        try:
            self.__leaks_details = pd.read_csv(file_leaks, index_col='Description')
        except:
            self.__leaks_details = pd.read_excel(file_leaks, index_col='Description')
        # Convert timestamps to indices
        self.__leaks_details.loc['Leak Start'] = self.__leaks_details.loc['Leak Start'].apply(self.__timestamp_to_idx)
        self.__leaks_details.loc['Leak End'] = self.__leaks_details.loc['Leak End'].apply(self.__timestamp_to_idx)
        self.__leaks_details.loc['Peak Time'] = self.__leaks_details.loc['Peak Time'].apply(self.__timestamp_to_idx)

    def get_leaks_details(self):
        if self.__leaks_details is None:
            self.__load_leaks_details()
        return self.__leaks_details.copy()


def normalize(X, dim=None, a=0, b=1, _min=None, _max=None):
    """ 
        Method to perform Min-Max normalization of the data.
    """
    E = 1e-12
    
    if dim:
        x, y, z = X.shape
        if _min is None:
            _min = X.min(dim=dim)[0].reshape(x, 1, z).repeat(1, y, 1)
        if _max is None:    
            _max = X.max(dim=dim)[0].reshape(x, 1, z).repeat(1, y, 1)
        X = (b - a) * ((X - _min) / (_max - _min + E)) + a
    else:
        if _min is None:
            _min = X.min()
        if _max is None:    
            _max = X.max()
        X = (b - a) * ((X - _min) / (_max - _min + E)) + a

    return X


def convert_to_bi_edges(edge_index, edge_attr=None):    
    """ 
        Method to convert directed edges to bi-directional edges.
    """    
    edge_index_swap = edge_index.clone()
    edge_index_swap[0,:] = edge_index[1,:]
    edge_index_swap[1,:] = edge_index[0,:]   
    edge_index_bi = torch.cat([edge_index, edge_index_swap], dim=1)
    if edge_attr is not None:
        edge_attr_bi = torch.cat([edge_attr, edge_attr], dim=1)
        return edge_index_bi, edge_attr_bi
    else:
        return edge_index_bi
    

def relabel_nodes(node_indices, edge_indices):
    """ Relabels node and edge indices starting from 0. """

    node_idx = np.where(node_indices >= 0)[0]
    edge_idx = copy.deepcopy(edge_indices)
    for idx, index in zip(node_idx, node_indices):
        edge_idx = np.where(edge_indices == index, idx, edge_idx)
    edge_idx = torch.tensor(edge_idx, dtype=int)

    return node_idx, edge_idx


def create_graph(inp_file, path_to_data, leak_path, PRVS=True, _demands=False):
    """ Creates the graph node features (X), node indices and edge indices.

        It requires a path to the Network Structure file *.inp (inp_file) 
        to retrieve the original node and edge indices.

        A path to the saved simulations *.csv files (path_to_data). 

        It returns an object with node feature matrix along with the  
        node and edge indices.    
     """

    """ Loading the WDS from the .inp file. """ 
    wn = wntr.network.WaterNetworkModel(inp_file)

    """ Getting pipe (edge) lengths and diameters and node indices. """ 
    edge_lengths = torch.tensor(wn.query_link_attribute('length').values, dtype=torch.float32)
    edge_dias = torch.tensor(wn.query_link_attribute('diameter').values, dtype=torch.float32)
    
    nodes_df = pd.DataFrame(wn.get_graph().nodes())
    node_indices = np.array(nodes_df.index)
    n_nodes = len(node_indices)
    
    """ Creating edge indices matrix. """ 
    n_lengths = len(edge_lengths)
    n_edges = n_lengths + 4   # PRVs and pump do not have lengths
    all_edge_indices = np.zeros((2, n_edges), dtype=int)
    for idx, (name, link) in enumerate(wn.links()):
        all_edge_indices[0, idx] = nodes_df.loc[nodes_df[0] == link.start_node_name].index.values
        all_edge_indices[1, idx] = nodes_df.loc[nodes_df[0] == link.end_node_name].index.values

    """ 
        Loading pressure values as node features and changing the 
        sampling frequency to every 15 mins from every 5 mins. 
    """     
    scenario = WaterFutureScenario(path_to_data, leak_path)        
    X_df = scenario.get_pressures()
    resample_idx = range(0, X_df.shape[0], 3)

    if _demands:
        XD_df = scenario.get_demands()
        X = torch.zeros(len(resample_idx), n_nodes, 2, dtype=torch.float32)
        X[:, :, 1] = torch.tensor(XD_df.astype("float32").values[resample_idx,:n_nodes], dtype=torch.float32)      
    else:
        X = torch.zeros(len(resample_idx), n_nodes, 1, dtype=torch.float32)
    X[:, :, 0] = torch.tensor(X_df.astype("float32").values[resample_idx,:n_nodes], dtype=torch.float32)      
    
    """ Relabeling node and edge indices. """ 
    node_indices_orig, edge_indices_orig = relabel_nodes(node_indices, all_edge_indices)

    """ Creating edge attributes matrix. """ 
    edge_attr_orig = torch.zeros(X.shape[0], edge_indices_orig.shape[1], 2, dtype=torch.float32)
    edge_attr_orig[:, :n_lengths, 0] = edge_lengths
    edge_attr_orig[:, :n_lengths, 1] = edge_dias[:n_lengths]
    edge_attr_orig[:, n_lengths+1:, 1] = edge_dias[n_lengths:]
    
    """ Dropping water source (tanks, reservoirs). """ 
    X = X[:,:-3,:]
    node_indices = node_indices_orig[:-3]
    edge_attr = edge_attr_orig[:, edge_indices_orig[0,:] < (n_nodes-3), :]
    edge_indices = edge_indices_orig[:, edge_indices_orig[0,:] < (n_nodes-3)]
    edge_attr = edge_attr[:, edge_indices[1,:] < (n_nodes-3), :]
    edge_indices = edge_indices[:, edge_indices[1,:] < (n_nodes-3)]

    edge_indices_1 = torch.tensor([[53],[342]])
    edge_indices = torch.cat((edge_indices, edge_indices_1), dim=1)
    out_1, out_2 = np.where(edge_indices_orig[0,:] == 53)[0], np.where(edge_indices_orig[1,:] == 784)[0]
    ea_idx_out = np.intersect1d(out_1, out_2)
    in_1, in_2 = np.where(edge_indices_orig[0,:] == 784)[0], np.where(edge_indices_orig[1,:] == 342)[0]
    ea_idx_in = np.intersect1d(in_1, in_2)
    edge_attr_1_out = edge_attr_orig[:, ea_idx_out, :]
    edge_attr_1_in = edge_attr_orig[:, ea_idx_in, :]
    edge_attr_1 = torch.zeros_like(edge_attr_1_out)
    edge_attr_1[:, :, 0] = edge_attr_1_out[:, :, 0] + edge_attr_1_in[:, :, 0]
    edge_attr_1[:, :, 1] = edge_attr_1_out[:, :, 1] + edge_attr_1_in[:, :, 1]
    edge_attr = torch.cat((edge_attr, edge_attr_1), dim=1)       

    """ Adding the PRV mask to the edge attributes matrix. """ 
    edge_attr_add = torch.zeros(X.shape[0], edge_indices.shape[1], 1, dtype=torch.float32)
    edge_attr_add[:, -4:-1, 0] = 1.
    edge_attr = torch.cat((edge_attr, edge_attr_add), dim=-1)            

    """ Converting directed edges and attributes to bi-directional / undirected. """ 
    edge_indices, edge_attr = convert_to_bi_edges(edge_indices, edge_attr)    

    anomalies_df = scenario.get_leaks_details() 
    anomalies_edge_idx = int("".join(list(anomalies_df["Value"][0])[1:])) - 1
    anomalies_nodes_ids = edge_indices_orig[:, anomalies_edge_idx].tolist()

    """ Creating and returning an object with node feature matrix along with the  
        node and edge indices. """ 
    wdn_graph = WDN_Graph(X, node_indices, edge_indices, edge_attr, anomalies_nodes_ids, anomalies_df)
    return wdn_graph, X_df.index[::3]


class WDN_Graph():
    """ 
        Object with node feature matrix and node and edge indices. 
    """ 
    def __init__(self, X, node_indices, edge_indices, edge_attr, anomalies_nodes_ids, anomalies_df):
        super().__init__()   
        self.X = X
        self.node_indices = node_indices     
        self.edge_indices = edge_indices
        self.edge_attr = edge_attr        
        self.anomalies_nodes_ids = anomalies_nodes_ids
        self.anomalies_df = anomalies_df

   
class WDN_Dataset_IM(InMemoryDataset):
    """ 
        InMemory Dataset Object.

        Creates a list of separate graphs for each sample. 
        Each graph is characterized by:
            a masked node feature matrix:       x
            an unmasked node feature matrix:    y
            an edge indices matrix:             edge_index
            an edge attributes matrix:          edge_attr
    """ 
    def __init__(self, ):
        super().__init__()        

    def len(self):
        return len(self._data_list)
    
    def get(self, idx):
        wdn_graph = self.data[idx]
        return wdn_graph

    def load(self, X, mask, edge_indices, edge_attr):
        
        self.data = []
        Y = X.clone()
        
        for idx in self._data_list:            
            wdn_graph = Data()
            x = X[idx, :, :] 
            y = Y[idx, :, :]  
            wdn_graph.x = x
            wdn_graph.edge_attr = edge_attr[idx, :, :]
            wdn_graph.edge_index = edge_indices
            wdn_graph.y = y        
            
            wdn_graph.x[mask[:,0] == 0, :] = 0 
            
            self.data.append(wdn_graph)
        return Y


def load_dataset(X, n_nodes, installed_sensors, edge_indices, edge_attr):
    """ 
        Creating and loading the dataset.
    """
    mask = torch.zeros((n_nodes, 1), dtype=torch.float32)  
    mask[installed_sensors] = 1 

    dataset = WDN_Dataset_IM()
    dataset._data_list = np.arange(X.shape[0])
    Y = dataset.load(X, mask, edge_indices, edge_attr)    
    return dataset, Y  
    

def plot_errors(Y, Y_hat, args, save_dir=None, flag="test", plot=True):
    """
        Plots the Absolute Relative Errors for all nodes.
    """

    n_nodes = Y_hat.shape[1]
    norm_abs_errors = ((Y - Y_hat).abs() / Y)
    mean_abs_errors = norm_abs_errors.mean(dim=0)
    p_coefs = np.zeros(n_nodes)
    for node in range(n_nodes):
        p_coefs[node] = pearson_coef(Y[:, node], Y_hat[:, node])
    t = np.arange(n_nodes)
    
    if plot:
        plt.figure(figsize=(20, 12))
        plt.scatter(t, mean_abs_errors, label="Absolute Relative Error", color='r')
        plt.title('Absolute relative error for all nodes', size=24)
        plt.xlabel('Nodes', size=16)
        plt.ylabel('Absolute Error', size=16)
        plt.xticks(size=16)
        plt.yticks(size=16)
        plt.tight_layout()

        plt.savefig(save_dir+"/plot_errors_"+args.model+"_"+str(args.n_aggr)+"_"+str(args.n_hops)+"_"+str(datetime.date.today())+"_"+flag+".jpg")
        plt.close()

    return mean_abs_errors, norm_abs_errors, p_coefs


def pearson_coef(y, y_predict):
    """
        Computes the Pearson Correlation Coefficient.
    """
    y_diff = y - y.mean(dim=0)
    y_predict_diff = y_predict - y_predict.mean(dim=0)
    p_coef = (y_diff * y_predict_diff).sum(dim=0) / \
            (torch.sqrt((y_diff ** 2).sum(dim=0)) * torch.sqrt((y_predict_diff ** 2).sum(dim=0)) + 1e-12)
    return p_coef


def plot_graph(inp_file, e_index, args, save_dir="", node_errors=[], plot=True, 
               labels=True, cmap="summer", flag="orig", edge_errors=None, edge_cmap='Reds', 
               node_size=125, font_size=10, edge_font_size=10, edge_names=None, width=3):
    """
        Plots the WDS with a spectrum of colors indicating the level of error for every node
    """
    wn = wntr.network.WaterNetworkModel(inp_file)
    G = nx.DiGraph()
    edge_list = [ (u, v) for u, v in zip(*e_index.numpy()) ]
    G.add_edges_from(edge_list)

    if plot:
        pos = wn.query_node_attribute('coordinates').values[:-3]

        fig, ax = plt.subplots(figsize=(120, 75))
        node_color = normalize(node_errors)
        if edge_errors is not None:
            edge_color = edge_errors #(normalize(edge_errors, a=0.25))
        else:
            edge_color = 'k'
        edge_cmap = mpl.cm.get_cmap(name=edge_cmap)

        print(edge_cmap)

        nx.draw_networkx(G, 
            pos=pos,
            node_color=list(node_color),
            nodelist=range(G.number_of_nodes()),
            cmap=cmap,
            node_size=node_size, 
            ax=ax,
            edgelist=edge_list,
            width=width, 
            edge_color=edge_color, 
            edge_vmin=0., 
            edge_vmax=1.,  
            edge_cmap=edge_cmap,
            with_labels=labels,
            font_size=font_size,
            arrows=True,
            )
        if edge_names is not None:
            edge_labels = { (u, v) : e for u, v, e in zip(*np.array(e_index), np.array(edge_names)) }
            nx.draw_networkx_edge_labels(G,
                pos = pos,
                edge_labels = edge_labels,
                font_size = edge_font_size,
            )
        plt.savefig(save_dir+"/_graph_"+str(args.n_aggr)+"_"+str(args.n_hops)+"_"+str(datetime.date.today())+"_"+flag+".jpg")
        plt.close()
    

