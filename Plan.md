# Grid:
## HTCondor
What is required here?

## Kubernetes for managing containers?
Basic of Kubernetes

# Language Model
A small Visual language model should be downloaded from Ollama. It should be installed in a shared resource node on the lab. Workers should have access to load the model into their memory, whenever a request to process a job arises.

## Setup System-prompt
After downloading the model, it may need some minor configuration. Model performance is not really in focus, but basic job descriptions will likely be necessary so that the model knows what it is supposedto do with the documents.

# Middleware
Some method must be developed for how we submit our jobs, and should be performed on a higher level than just submitting HTCondor jobs directly. We can create a small interface or program that allows the user to send a file, or set of files. And should generate separate jobs for each.
Should there be hierarchies for jobs? So first level should load model, and second level should process documents?

# Testing 
Test cases should be implemented in the form of mock-documents, Ideally I can format these in the same way as actual patient data format. The system prompt should ideally allow the model to provide a description of pre-definite document types along with confidence scores. It should therefore be able to reject non-relevant documents

