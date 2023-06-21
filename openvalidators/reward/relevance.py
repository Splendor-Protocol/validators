
# The MIT License (MIT)
# Copyright © 2021 Yuma Rao

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import torch
from .reward import BaseRewardModel
from transformers import  AutoTokenizer, AutoModel

class BertRelevanceRewardModel( BaseRewardModel ):

    relevance_model_path = "bert-base-uncased"

    @property
    def name(self) -> str: return "bert-embedding-relevance-scoring"
   
    def __init__( self, device: str ):
        super().__init__()
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(BertRelevanceRewardModel.relevance_model_path)
        self.model = AutoModel.from_pretrained(BertRelevanceRewardModel.relevance_model_path).to(self.device)

    def mean_pooling(model_output, attention_mask):
        """Applies mean pooling to the token embeddings generated by the model.
        Args:
            model_output (torch.Tensor): Embedding model output, where the first element contains token embeddings.
            attention_mask (torch.Tensor): Attention mask to indicate valid tokens.
        Returns:
            torch.Tensor: Mean-pooled representation of the token embeddings.
        Notes:
            - The function calculates the mean-pooled representation using the attention mask for valid tokens.
            - Input_mask_expanded is created by expanding the attention mask to match the size of token embeddings.
            - The result is obtained by summing the element-wise multiplication of embeddings and input_mask_expanded,
                and dividing it by the sum of input_mask_expanded after clamping its values to a minimum of 1e-9.
        """
        token_embeddings = model_output[0]
        input_mask_expanded = (
            attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        )
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
            input_mask_expanded.sum(1), min=1e-9
        )

    def get_embedding(self, message: str) -> "torch.FloatTensor":
        """Runs a forward pass through the model.
        Args:
            message (:obj:`str`):
                text message to be encoded.
        Returns:
            embedding (:obj:`torch.FloatTensor`):
                Embedding for the message.
        """
        encoded_input = self.tokenizer(
            message,
            padding=True,
            truncation=True,
            return_overflowing_tokens=True,
            return_tensors="pt",
        ).to(self.device)

        # Pop the overflow mapping from the input to maintain the expected { input_ids, mask } format of the model
        _ = encoded_input.pop("overflow_to_sample_mapping")

        with torch.no_grad():
            embeddings = self.model(**encoded_input)

        sentence_embeddings = BertRelevanceRewardModel.mean_pooling(embeddings, encoded_input["attention_mask"])
        sentence_embeddings = torch.nn.functional.normalize(sentence_embeddings, p=2, dim=1)
        batch_representation = torch.mean(sentence_embeddings, dim=0)
        return batch_representation
    

    def reward( self, prompt: str, completion: str, name: str ) -> float:

        # Get the two bert embeddings.
        completion_embedding = self.get_embedding( completion)
        prompt_embedding = self.get_embedding( prompt)

        # Calculate the RMSE distance for the 2 embeddings.
        diff = (( completion_embedding - prompt_embedding )**2).mean()**0.5

        # Return relevance scoring.
        return float(-diff)
